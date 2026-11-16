"""The new tool pieces against the seeded Kestrel API (and one offline timeout)."""

import httpx
from ch07.model_client import ToolCall
from ch07.tools import build_registry


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(id="call_1", name=name, arguments=arguments)


def test_list_shipments_returns_late_rows_for_one_carrier(kestrel_url):
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        result = build_registry(http).dispatch(
            call("list_shipments", carrier="Northline Freight", limit=3)
        )
    assert not result.is_error and result.content.startswith("<data>[")
    assert result.content.count('"carrier": "Northline Freight"') == 3
    assert result.content.count('"late": true') == 3


def test_limit_above_20_is_rejected_before_any_request():
    requests = []
    http = httpx.Client(
        base_url="http://kestrel.test",
        transport=httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200)),
    )
    result = build_registry(http).dispatch(call("list_shipments", limit=500))
    assert result.is_error and "limit" in result.content and requests == []


def test_a_timeout_is_reported_as_worth_one_retry():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    http = httpx.Client(base_url="http://kestrel.test", transport=httpx.MockTransport(handler))
    result = build_registry(http).dispatch(call("get_order", order_id="O-0014614"))
    assert result.is_error
    assert result.content == "get_order timed out. Retry once; if it fails again, report it."


def test_unknown_order_is_a_permanent_error(kestrel_url):
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        result = build_registry(http).dispatch(call("get_order", order_id="O-9999999"))
    assert (result.is_error, result.content) == (True, "No order O-9999999 exists.")
