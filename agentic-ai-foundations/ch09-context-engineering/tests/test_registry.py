"""The dispatcher's two changes: field-level validation messages with hints."""

import httpx
from ch09.model_client import ToolCall
from ch09.registry import Tool, ToolRegistry
from ch09.tools import GetDeliveryStatusArgs, ListShipmentsArgs, build_registry


def call(tool: str, **arguments) -> ToolCall:
    return ToolCall(id="call_1", name=tool, arguments=arguments)


def recording_client(requests: list) -> httpx.Client:
    handler = lambda r: requests.append(r) or httpx.Response(200, json=[])  # noqa: E731
    return httpx.Client(base_url="http://kestrel.test", transport=httpx.MockTransport(handler))


def test_out_of_range_limit_is_rejected_before_any_request(tmp_path):
    from datetime import date

    from ch09.return_store import ReturnStore

    requests: list = []
    registry = build_registry(
        recording_client(requests), ReturnStore(str(tmp_path / "r.sqlite")), date(2025, 12, 16)
    )
    result = registry.dispatch(call("list_shipments", limit=500))
    assert result.is_error and requests == []
    assert result.content == (
        "Invalid arguments for list_shipments. "
        "limit: Input should be less than or equal to 50; got 500."
    )


def test_a_hint_is_added_to_the_field_it_belongs_to():
    registry = ToolRegistry()
    registry.register(
        Tool(
            "get_delivery_status",
            "",
            GetDeliveryStatusArgs,
            lambda a: {},
            {"order_or_ticket_id": "Use O- or T-."},
        )
    )
    result = registry.dispatch(call("get_delivery_status", order_or_ticket_id="42"))
    assert result.is_error
    assert "order_or_ticket_id:" in result.content and "got '42'" in result.content
    assert result.content.endswith("Use O- or T-.")


def test_missing_field_does_not_echo_the_whole_input():
    registry = ToolRegistry()
    registry.register(Tool("get_delivery_status", "", GetDeliveryStatusArgs, lambda a: {}))
    result = registry.dispatch(call("get_delivery_status", other="x" * 500))
    assert "order_or_ticket_id: required, not provided." in result.content
    assert "xxxx" not in result.content


def test_long_values_are_cut_short_in_the_message():
    registry = ToolRegistry()
    registry.register(Tool("list_shipments", "", ListShipmentsArgs, lambda a: {}))
    result = registry.dispatch(call("list_shipments", carrier="Z" * 1000))
    assert result.is_error and len(result.content) < 400


def test_unknown_tool_lists_the_available_ones():
    registry = ToolRegistry()
    registry.register(Tool("get_ticket", "", ListShipmentsArgs, lambda a: {}))
    result = registry.dispatch(call("get_order"))
    assert (result.is_error, result.content) == (
        True,
        "Unknown tool: get_order. Available tools: get_ticket.",
    )
