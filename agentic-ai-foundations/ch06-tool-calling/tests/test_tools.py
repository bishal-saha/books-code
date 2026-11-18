"""The registry and dispatcher: every outcome is a ToolResult carrying the call's id."""

import httpx
import pytest
from ch06.model_client import ToolCall
from ch06.tools import MAX_RESULT_CHARS, OrderIdArgs, Tool, ToolRegistry, build_registry


def offline_http(handler) -> httpx.Client:
    """An httpx client whose requests go to a Python function, not the network."""
    return httpx.Client(base_url="http://kestrel.test", transport=httpx.MockTransport(handler))


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(id="call_1", name=name, arguments=arguments)


def test_definitions_come_from_the_args_model():
    registry = build_registry(offline_http(lambda r: httpx.Response(500)))
    defs = {d.name: d for d in registry.definitions()}
    assert set(defs) == {"get_order", "get_shipment"}
    schema = defs["get_order"].input_schema
    assert schema["type"] == "object"
    assert schema["required"] == ["order_id"]
    assert schema["properties"]["order_id"]["pattern"] == r"^O-\d{7}$"


def test_duplicate_names_fail_at_startup():
    registry = ToolRegistry()
    tool = Tool("get_order", "x", OrderIdArgs, lambda args: {})
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_unknown_tool_becomes_an_error_result():
    registry = build_registry(offline_http(lambda r: httpx.Response(500)))
    result = registry.dispatch(call("cancel_order", order_id="O-0000141"))
    assert (result.tool_call_id, result.is_error) == ("call_1", True)
    assert "Available tools: get_order, get_shipment" in result.content


def test_invalid_arguments_never_reach_the_function():
    requests = []
    registry = build_registry(offline_http(lambda r: requests.append(r) or httpx.Response(200)))
    result = registry.dispatch(call("get_order", order_id="42"))
    assert result.is_error and result.content.startswith("Invalid arguments: order_id:")
    assert requests == []


def test_tool_error_message_is_shown_and_other_failures_are_sanitised():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/shipment"):
            return httpx.Response(404, json={"error": "order O-0017612 has not shipped"})
        return httpx.Response(500, json={"error": "db password=hunter2"})

    registry = build_registry(offline_http(handler))
    shipment = registry.dispatch(call("get_shipment", order_id="O-0017612"))
    assert shipment.content == "No shipment for O-0017612: order O-0017612 has not shipped."
    order = registry.dispatch(call("get_order", order_id="O-0017612"))
    assert order.is_error and order.content == "get_order failed (HTTPStatusError)."


def test_success_is_delimited_data_and_long_output_is_truncated():
    registry = ToolRegistry()
    registry.register(Tool("big", "x", OrderIdArgs, lambda args: {"note": "<b>" * 5000}))
    result = registry.dispatch(call("big", order_id="O-0000001"))
    assert not result.is_error
    assert result.content.startswith("<data>") and result.content.endswith("</data>")
    assert "<b>" not in result.content.removeprefix("<data>").removesuffix("</data>")
    assert "[truncated]" in result.content
    assert len(result.content) < MAX_RESULT_CHARS + 200


def test_against_the_seeded_kestrel_api(kestrel_url):
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        registry = build_registry(http)
        order = registry.dispatch(call("get_order", order_id="O-0000141"))
        missing = registry.dispatch(call("get_shipment", order_id="O-0017612"))
    assert '"customer_id": "C-001755"' in order.content
    assert '"status": "shipped"' in order.content
    assert missing.is_error and "has not shipped" in missing.content


def test_four_bad_calls_against_the_seeded_kestrel_api(kestrel_url):
    """The four error results printed in the chapter, one per kind of bad call."""
    bad_calls = [
        ToolCall(id="call_1", name="get_order", arguments={"order_id": "O-42"}),
        ToolCall(id="call_2", name="cancel_order", arguments={"order_id": "O-0000141"}),
        ToolCall(id="call_3", name="get_shipment", arguments={"order_id": "O-0017612"}),
        ToolCall(id="call_4", name="get_order", arguments={"order_id": "O-9999999"}),
    ]
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        registry = build_registry(http)
        lines = [registry.dispatch(c).model_dump_json() for c in bad_calls]
    for line in lines:
        print(line)
    assert lines == [
        r"""{"tool_call_id":"call_1","content":"Invalid arguments: order_id: String should match pattern '^O-\\d{7}$'","is_error":true}""",  # noqa: E501
        """{"tool_call_id":"call_2","content":"Unknown tool: cancel_order. Available tools: get_order, get_shipment.","is_error":true}""",  # noqa: E501
        """{"tool_call_id":"call_3","content":"No shipment for O-0017612: order O-0017612 has not shipped.","is_error":true}""",  # noqa: E501
        """{"tool_call_id":"call_4","content":"No order O-9999999 exists.","is_error":true}""",
    ]
