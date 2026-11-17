"""search_web over the offline search service: retries, fees, and one clear error result."""

from decimal import Decimal

import httpx
import pytest
from ch16.budget import BudgetTracker, RunBudget
from ch16.offline import OfflineSearchService
from ch16.registry import ToolError
from ch16.scripted import ILLUSTRATIVE
from ch16.tools import HttpSearchBackend, SearchRetries, SearchWebArgs, search_web
from pydantic import SecretStr

ARGS = SearchWebArgs(query="Harbour Express delivery reviews")


def tracker(max_cost: str | None = "0.50") -> BudgetTracker:
    budget = RunBudget(8, 60_000, 120.0, Decimal(max_cost) if max_cost else None)
    return BudgetTracker(budget, price=ILLUSTRATIVE, search_usd_per_query=Decimal("0.005"))


def retries(t: BudgetTracker) -> SearchRetries:
    return SearchRetries(timeout_s=10.0, tracker=t, sleep=lambda s: None)


def test_a_503_is_retried_and_both_requests_are_charged() -> None:
    service, t = OfflineSearchService(statuses=[503]), tracker()
    hits = search_web(ARGS, service.backend(), retries(t))
    assert hits[0]["url"] == "https://reviews.example.com/harbour-express"
    assert len(service.requests) == 2 and t.search_usd == Decimal("0.010")


def test_a_refusal_is_one_request_and_one_clear_error() -> None:
    service, t = OfflineSearchService(then=401), tracker()
    with pytest.raises(ToolError, match=r"refused \(HTTP 401\); retrying won't help"):
        search_web(ARGS, service.backend(), retries(t))
    assert len(service.requests) == 1


def test_a_service_that_stays_down_gets_max_attempts() -> None:
    service, t = OfflineSearchService(then=503), tracker()
    with pytest.raises(ToolError, match=r"failed \(HTTP 503\) after up to 3 tries"):
        search_web(ARGS, service.backend(), retries(t))
    assert len(service.requests) == 3 and t.search_requests == 3


def test_results_null_is_a_clear_error_not_a_crash() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": None})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = HttpSearchBackend("https://search.invalid/v1", SecretStr("k"), client)
    with pytest.raises(ToolError, match="no results list"):
        search_web(ARGS, backend, retries(tracker()))


def test_no_request_is_sent_when_money_cannot_cover_it() -> None:
    service, t = OfflineSearchService(), tracker(max_cost="0.004")  # less than one search
    with pytest.raises(ToolError, match="money budget can't cover another search"):
        search_web(ARGS, service.backend(), retries(t))
    assert service.requests == [] and t.search_requests == 0


def test_a_rejected_query_lets_the_model_try_another() -> None:
    service, t = OfflineSearchService(then=400), tracker()
    with pytest.raises(ToolError, match=r"rejected this query \(HTTP 400\)\. Try one shorter"):
        search_web(ARGS, service.backend(), retries(t))
    assert len(service.requests) == 1  # permanent for this query: not retried in code
