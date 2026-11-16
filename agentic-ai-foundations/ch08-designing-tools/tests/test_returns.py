"""create_return_authorisation: idempotency and business rules, on the seeded Kestrel API."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx
import pytest
from ch08.lookups import kestrel_client
from ch08.model_client import ToolCall
from ch08.return_store import ReturnStore
from ch08.returns import return_window_days
from ch08.tools import build_registry

TODAY = date(2025, 12, 16)
RETURN = {"ticket_id": "T-000410", "reason": "Doesn't fit."}


def ret(**arguments) -> ToolCall:
    return ToolCall(id="call_1", name="create_return_authorisation", arguments=arguments)


@pytest.fixture
def store(tmp_path) -> ReturnStore:
    return ReturnStore(str(tmp_path / "returns.sqlite"))


def test_a_repeat_returns_the_same_authorisation(kestrel_url, store):
    with kestrel_client(kestrel_url) as http:
        registry = build_registry(http, store, TODAY)
        first = registry.dispatch(ret(**RETURN, lines=[{"sku": "SKU-00042", "quantity": 2}]))
        # the same return, split across two lines
        again = registry.dispatch(ret(**RETURN, lines=[{"sku": "SKU-00042", "quantity": 1}] * 2))
    assert '"already_existed": false' in first.content and '"status": "pending"' in first.content
    assert '"already_existed": true' in again.content
    assert first.content.split('"ra_id": ')[1][:13] == again.content.split('"ra_id": ')[1][:13]
    assert store.count() == 1


def test_reordered_lines_are_the_same_return(kestrel_url, store):
    a = [{"sku": "SKU-00042", "quantity": 1}, {"sku": "SKU-00007", "quantity": 1}]
    with kestrel_client(kestrel_url) as http:
        registry = build_registry(http, store, TODAY)
        registry.dispatch(ret(**RETURN, lines=a))
        second = registry.dispatch(ret(**RETURN, lines=list(reversed(a))))
    assert '"already_existed": true' in second.content and store.count() == 1


def test_a_repeat_after_the_window_closed_still_gets_the_existing_one(kestrel_url, store):
    lines = [{"sku": "SKU-00042", "quantity": 1}]
    with kestrel_client(kestrel_url) as http:
        build_registry(http, store, TODAY).dispatch(ret(**RETURN, lines=lines))
        later = build_registry(http, store, date(2026, 3, 1)).dispatch(ret(**RETURN, lines=lines))
    assert not later.is_error and '"already_existed": true' in later.content


def test_parallel_identical_calls_leave_one_row(kestrel_url, store):
    lines = [{"sku": "SKU-00042", "quantity": 1}]
    with kestrel_client(kestrel_url) as http:
        registry = build_registry(http, store, TODAY)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(lambda _: registry.dispatch(ret(**RETURN, lines=lines)), range(4))
            )
    assert all(not r.is_error for r in results)
    assert sum('"already_existed": false' in r.content for r in results) == 1
    assert store.count() == 1


@pytest.mark.parametrize(
    ("ticket", "expected"),
    [
        ("T-000122", "30-day return window closed on 2025-12-13"),  # delivered 2025-11-13
        ("T-000407", "is shipped, not delivered yet"),  # Chapter 1's ticket: still in transit
        ("T-000458", "can't be confirmed"),  # a trade order: fail closed
        ("T-999999", "No ticket T-999999"),
    ],
)
def test_business_rules_refuse_and_write_nothing(kestrel_url, store, ticket, expected):
    with kestrel_client(kestrel_url) as http:
        result = build_registry(http, store, TODAY).dispatch(
            ret(
                ticket_id=ticket,
                reason="Changed my mind.",
                lines=[{"sku": "SKU-00042", "quantity": 1}],
            )
        )
    assert result.is_error and expected in result.content
    assert store.count() == 0


def test_window_parsing_fails_closed():
    policy = "Consumers may return unused items within 30 days of delivery; trade within 14 days."
    assert return_window_days(policy, "store") == 30
    assert return_window_days(policy, "trade") is None
    assert return_window_days("Consumers have a generous window.", "store") is None
    two = "Consumers may return within 30 days. Consumers in sales may return within 14 days."
    assert return_window_days(two, "store") is None


def test_a_policy_that_cannot_be_parsed_writes_nothing(store):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/tickets/"):
            return httpx.Response(200, json={"ticket_id": "T-000410", "order_id": "O-0013196"})
        if path == "/orders/O-0013196":
            return httpx.Response(200, json={"status": "delivered", "channel": "store"})
        if path.endswith("/shipment"):
            return httpx.Response(200, json={"delivered_at": "2025-12-14T10:00:00+00:00"})
        return httpx.Response(200, json={"name": "returns-policy", "body": "Ask support."})

    http = httpx.Client(base_url="http://kestrel.test", transport=httpx.MockTransport(handler))
    result = build_registry(http, store, TODAY).dispatch(
        ret(**RETURN, lines=[{"sku": "SKU-00042", "quantity": 1}])
    )
    assert result.is_error and "Don't retry" in result.content and store.count() == 0
