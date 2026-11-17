"""The adapter: the per-call timeout (Chapter 7) and count_tokens (new in Chapter 9)."""

import json
from decimal import Decimal

import anthropic
import httpx2  # the HTTP library the anthropic SDK is built on
from ch09.anthropic_adapter import AnthropicAdapter
from ch09.model_client import Message, ToolDefinition
from ch09.settings import Settings

SETTINGS = Settings(
    model="test-model",
    api_key="test-key",
    input_price_per_mtok=Decimal("2"),
    output_price_per_mtok=Decimal("10"),
    timeout_seconds=30.0,
    max_retries=0,
)
REPLY = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "test-model",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


def read_timeout_of_one_call(**kwargs) -> float:
    seen: dict = {}

    def handler(request):
        seen.update(request.extensions["timeout"])
        return httpx2.Response(200, json=REPLY)

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    adapter = AnthropicAdapter(SETTINGS, http_client=http)
    adapter.complete("sys", [Message(role="user", content="q")], 50, **kwargs)
    return seen["read"]


def test_per_call_timeout_overrides_the_client_default():
    assert read_timeout_of_one_call(timeout=12.5) == 12.5


def test_no_timeout_keeps_the_client_wide_setting():
    assert read_timeout_of_one_call() == 30.0


def test_count_tokens_posts_the_same_request_shape_to_the_count_endpoint():
    seen: dict = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["timeout"] = request.extensions["timeout"]["read"]
        return httpx2.Response(200, json={"input_tokens": 42})

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    adapter = AnthropicAdapter(SETTINGS, http_client=http)
    tool = ToolDefinition(name="t", description="d", input_schema={"type": "object"})
    count = adapter.count_tokens("sys", [Message(role="user", content="q")], [tool], timeout=5.0)
    assert count == 42 and adapter.provider_counts
    assert seen["path"] == "/v1/messages/count_tokens"
    assert seen["body"]["model"] == "test-model"  # counts are model-specific
    assert seen["body"]["system"] == "sys" and seen["body"]["tools"][0]["name"] == "t"
    assert seen["timeout"] == 5.0


def test_count_tokens_leaves_out_an_empty_system_prompt_and_no_tools():
    bodies: list = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json={"input_tokens": 3})

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    AnthropicAdapter(SETTINGS, http_client=http).count_tokens(
        "", [Message(role="user", content=".")]
    )
    assert "system" not in bodies[0] and "tools" not in bodies[0]
