"""The tools on their own: the request each one sends and what the model would see."""

import httpx
from ch13.kestrel_tools import build_ops_registry
from ch13.model_client import ToolCall


def kestrel(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/shipments":
        return httpx.Response(200, json=[{"shipment_id": "S-0000011", "late": True}])
    if request.url.path == "/orders/O-9999999":
        return httpx.Response(404, json={"error": "no order O-9999999"})
    return httpx.Response(500, json={"error": "unexpected path"})


def make_registry(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return kestrel(request)

    http = httpx.Client(base_url="http://kestrel.test", transport=httpx.MockTransport(handler))
    return build_ops_registry(http)


def test_list_shipments_sends_the_filters():
    seen: list[httpx.Request] = []
    call = ToolCall(id="c1", name="list_shipments", arguments={"carrier": "Swiftway Parcel"})
    result = make_registry(seen).dispatch(call)
    assert seen[0].url.params["carrier"] == "Swiftway Parcel"
    assert seen[0].url.params["late"] == "true"
    assert seen[0].url.params["limit"] == "10"
    assert not result.is_error and "S-0000011" in result.content


def test_unknown_order_is_a_result_the_model_can_act_on():
    call = ToolCall(id="c2", name="get_order", arguments={"order_id": "O-9999999"})
    result = make_registry([]).dispatch(call)
    assert result.is_error and result.tool_call_id == "c2"
    assert result.content == "No order O-9999999 exists."


def test_bad_arguments_never_reach_the_api():
    seen: list[httpx.Request] = []
    call = ToolCall(id="c3", name="get_stock", arguments={"sku": "42"})
    result = make_registry(seen).dispatch(call)
    assert result.is_error and "sku" in result.content
    assert seen == []
