"""The adapter's one change: a per-call timeout reaches the SDK request, None keeps the default."""

from decimal import Decimal

import anthropic
import httpx2  # the HTTP library the anthropic SDK is built on
from ch07.anthropic_adapter import AnthropicAdapter
from ch07.model_client import Message
from ch07.settings import Settings

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
