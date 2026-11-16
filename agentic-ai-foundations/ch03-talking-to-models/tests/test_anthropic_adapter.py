"""The adapter against a fake HTTP transport: real SDK code, no network, no key."""

import json
from decimal import Decimal

import anthropic
import httpx2  # the HTTP library the anthropic SDK is built on
import pytest
from ch03.anthropic_adapter import AnthropicAdapter
from ch03.model_client import Message, ModelError, ModelResponse
from ch03.settings import Settings

SETTINGS = Settings(
    model="test-model",
    api_key="test-key",
    input_price_per_mtok=Decimal("2"),
    output_price_per_mtok=Decimal("10"),
    max_retries=0,
)
MESSAGES = [Message(role="user", content="Where is my order?")]


def message_json(stop_reason: str, **usage: int) -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "test-model",
        "content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "Maya."}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20, **usage},
    }


def adapter_for(handler, settings: Settings = SETTINGS) -> AnthropicAdapter:
    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return AnthropicAdapter(settings, http_client=http)


@pytest.mark.parametrize(
    "provider_value, neutral",
    [
        ("end_turn", "finished"),
        ("max_tokens", "truncated"),
        ("model_context_window_exceeded", "truncated"),
        ("tool_use", "tool_call"),
        ("refusal", "other"),
    ],
)
def test_stop_reasons_map_to_neutral_values(provider_value, neutral):
    def handler(request):
        return httpx2.Response(200, json=message_json(provider_value))

    assert adapter_for(handler).complete("sys", MESSAGES, 50).stop_reason == neutral


def test_text_blocks_are_joined_and_cached_input_is_counted():
    def handler(request):
        body = message_json("end_turn", cache_creation_input_tokens=30, cache_read_input_tokens=5)
        return httpx2.Response(200, json=body, headers={"request-id": "req_123"})

    response = adapter_for(handler).complete("sys", MESSAGES, 50)
    assert response.text == "Hello Maya."
    assert response.usage.input_tokens == 135
    assert response.request_id == "req_123"


def test_the_request_carries_system_messages_and_cap():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx2.Response(200, json=message_json("end_turn"))

    adapter_for(handler).complete("Be brief.", MESSAGES, 50)
    assert sent["system"] == "Be brief."
    assert sent["max_tokens"] == 50
    assert sent["messages"] == [{"role": "user", "content": "Where is my order?"}]


@pytest.mark.parametrize(
    "status, kind",
    [(401, "auth"), (403, "auth"), (429, "rate_limited"), (400, "bad_request"),
     (500, "provider_error")],
)  # fmt: skip
def test_status_errors_become_model_errors(status, kind):
    def handler(request):
        body = {"type": "error", "error": {"type": "x", "message": "no"}}
        return httpx2.Response(status, json=body, headers={"request-id": "req_err"})

    with pytest.raises(ModelError) as info:
        adapter_for(handler).complete("sys", MESSAGES, 50)
    assert (info.value.kind, info.value.request_id) == (kind, "req_err")


def test_a_timeout_is_a_timeout_not_a_connection_error():
    def handler(request):
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(ModelError) as info:
        adapter_for(handler).complete("sys", MESSAGES, 50)
    assert info.value.kind == "timeout"


def test_sdk_retries_are_bounded_by_settings():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(429, json={}, headers={"retry-after-ms": "1"})

    with pytest.raises(ModelError):
        adapter_for(handler, SETTINGS.model_copy(update={"max_retries": 2})).complete(
            "sys", MESSAGES, 50
        )
    assert len(calls) == 3  # one call, two retries


def sse(*events: dict) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


def text_delta(text: str) -> dict:
    return {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": text},
    }


def test_stream_yields_text_then_one_final_response():
    start = message_json("end_turn") | {"content": [], "stop_reason": None}
    body = sse(
        {"type": "message_start", "message": start},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        text_delta("Hi "),
        text_delta("Maya"),
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "max_tokens", "stop_sequence": None},
         "usage": {"output_tokens": 2}},
        {"type": "message_stop"},
    )  # fmt: skip

    def handler(request):
        headers = {"content-type": "text/event-stream", "request-id": "req_s"}
        return httpx2.Response(200, content=body, headers=headers)

    items = list(adapter_for(handler).stream("sys", MESSAGES, 50))
    assert items[:2] == ["Hi ", "Maya"]
    final = items[-1]
    assert isinstance(final, ModelResponse)
    assert (final.text, final.stop_reason, final.request_id) == ("Hi Maya", "truncated", "req_s")
    assert final.usage.output_tokens == 2
