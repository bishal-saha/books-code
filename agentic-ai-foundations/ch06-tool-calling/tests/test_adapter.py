"""The adapter against a fake HTTP transport: the real SDK builds and parses every request."""

import json
from decimal import Decimal

import anthropic
import httpx2  # the HTTP library the anthropic SDK is built on
import pytest
from ch06.anthropic_adapter import AnthropicAdapter, to_sdk_tool_choice
from ch06.model_client import (
    Message,
    ModelError,
    ToolCall,
    ToolChoice,
    ToolDefinition,
    ToolResult,
    assistant_message,
    tool_results_message,
)
from ch06.settings import Settings

SETTINGS = Settings(
    model="test-model",
    api_key="test-key",
    input_price_per_mtok=Decimal("2"),
    output_price_per_mtok=Decimal("10"),
    max_retries=0,
)
TOOL = ToolDefinition(
    name="get_order",
    description="Get one order.",
    input_schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
)
TOOL_USE_RESPONSE = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "test-model",
    "content": [
        {"type": "text", "text": "Checking both."},
        {"type": "tool_use", "id": "toolu_a", "name": "get_order", "input": {"order_id": "O-1"}},
        {"type": "tool_use", "id": "toolu_b", "name": "get_order", "input": {"order_id": "O-2"}},
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "usage": {"input_tokens": 100, "output_tokens": 20},
}


def adapter_for(handler) -> AnthropicAdapter:
    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return AnthropicAdapter(SETTINGS, http_client=http)


def test_tool_use_blocks_become_tool_calls():
    adapter = adapter_for(lambda request: httpx2.Response(200, json=TOOL_USE_RESPONSE))
    r = adapter.complete("sys", [Message(role="user", content="q")], 50, [TOOL])
    assert r.stop_reason == "tool_call"
    assert r.text == "Checking both."
    assert [(c.id, c.arguments) for c in r.tool_calls] == [
        ("toolu_a", {"order_id": "O-1"}),
        ("toolu_b", {"order_id": "O-2"}),
    ]


def test_the_follow_up_request_on_the_wire():
    sent: dict = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx2.Response(200, json=TOOL_USE_RESPONSE)

    adapter = adapter_for(handler)
    first = adapter.complete("sys", [Message(role="user", content="q")], 50, [TOOL])
    results = [ToolResult(tool_call_id=c.id, content="{}") for c in first.tool_calls]
    history = [Message(role="user", content="q"), assistant_message(first)]
    history.append(tool_results_message(results))
    adapter.complete("sys", history, 50, [TOOL], ToolChoice(mode="none"))

    assert sent["tools"] == [TOOL.model_dump()]
    assert sent["tool_choice"] == {"type": "none"}
    assert sent["messages"][1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Checking both."},
            {
                "type": "tool_use",
                "id": "toolu_a",
                "name": "get_order",
                "input": {"order_id": "O-1"},
            },
            {
                "type": "tool_use",
                "id": "toolu_b",
                "name": "get_order",
                "input": {"order_id": "O-2"},
            },
        ],
    }
    assert sent["messages"][2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "toolu_a", "content": "{}", "is_error": False},
            {"type": "tool_result", "tool_use_id": "toolu_b", "content": "{}", "is_error": False},
        ],
    }


def test_no_tools_means_chapter_3s_request():
    sent: dict = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx2.Response(200, json=TOOL_USE_RESPONSE)

    adapter_for(handler).complete("sys", [Message(role="user", content="q")], 50)
    assert "tools" not in sent and "tool_choice" not in sent
    assert sent["messages"] == [{"role": "user", "content": "q"}]


@pytest.mark.parametrize(
    "choice, expected",
    [
        (ToolChoice(), {"type": "auto"}),
        (ToolChoice(mode="required"), {"type": "any"}),
        (ToolChoice(mode="tool", tool_name="get_order"), {"type": "tool", "name": "get_order"}),
        (ToolChoice(mode="none"), {"type": "none"}),
        (ToolChoice(allow_parallel=False), {"type": "auto", "disable_parallel_tool_use": True}),
        (
            ToolChoice(mode="required", allow_parallel=False),
            {"type": "any", "disable_parallel_tool_use": True},
        ),
        (ToolChoice(mode="none", allow_parallel=False), {"type": "none"}),
    ],
)
def test_tool_choice_mapping(choice, expected):
    assert to_sdk_tool_choice(choice) == expected


def test_forced_tool_without_a_name_is_a_programming_error():
    with pytest.raises(ValueError, match="tool_name"):
        to_sdk_tool_choice(ToolChoice(mode="tool"))


def test_a_rejected_tool_choice_is_reported_as_bad_request():
    def handler(request):
        body = {"type": "error", "error": {"type": "invalid_request_error", "message": "no"}}
        return httpx2.Response(400, json=body)

    with pytest.raises(ModelError) as info:
        adapter_for(handler).complete(
            "sys", [Message(role="user", content="q")], 50, [TOOL], ToolChoice(mode="required")
        )
    assert info.value.kind == "bad_request"


def test_tool_call_ids_round_trip_unchanged():
    call = ToolCall(id="toolu_01A09q90qw90lq917835lq9", name="get_order", arguments={})
    assert (
        tool_results_message([ToolResult(tool_call_id=call.id, content="x")])
        .tool_results[0]
        .tool_call_id
        == call.id
    )
