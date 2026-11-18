"""The native path: what the adapter sends, against a fake HTTP transport (real SDK, no key)."""

import json
from decimal import Decimal

import anthropic
import httpx2  # the HTTP library the anthropic SDK is built on
import pytest
from ch05.anthropic_adapter import AnthropicAdapter
from ch05.model_client import Message
from ch05.models import ExpenseClaim
from ch05.sample_replies import VALID_JSON
from ch05.settings import Settings
from pydantic import BaseModel, ValidationError

SETTINGS = Settings(
    model="test-model", api_key="test-key", input_price_per_mtok=Decimal("1"),
    output_price_per_mtok=Decimal("5"), max_retries=0,
)  # fmt: skip
MESSAGES = [Message(role="user", content="<claim>...</claim>")]


def reply(stop_reason: str, text: str) -> httpx2.Response:
    return httpx2.Response(200, json={
        "id": "msg_test", "type": "message", "role": "assistant", "model": "test-model",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason,
        "stop_sequence": None, "usage": {"input_tokens": 900, "output_tokens": 60},
    })  # fmt: skip


def send(output_format: type[BaseModel] | None, stop_reason: str, text: str) -> tuple[dict, str]:
    sent: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.update(json.loads(request.content))
        return reply(stop_reason, text)

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    adapter = AnthropicAdapter(SETTINGS, output_format=output_format, http_client=http)
    return sent, adapter.complete("system", MESSAGES, 400).stop_reason


def test_prompt_only_requests_carry_no_output_config() -> None:
    sent, _ = send(None, "end_turn", VALID_JSON)
    assert "output_config" not in sent


def test_thinking_is_disabled_by_default() -> None:
    sent, _ = send(None, "end_turn", VALID_JSON)
    assert SETTINGS.thinking == "off"
    assert sent["thinking"] == {"type": "disabled"}


def test_native_requests_carry_the_transformed_schema() -> None:
    sent, stop_reason = send(ExpenseClaim, "end_turn", VALID_JSON)
    fmt = sent["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"] == anthropic.transform_schema(ExpenseClaim)
    number = fmt["schema"]["properties"]["amount"]["anyOf"][0]
    assert "exclusiveMinimum" not in number  # moved into the description by the SDK
    assert number["description"] == "{exclusiveMinimum: 0.0}"
    assert stop_reason == "finished"


def test_a_refusal_on_the_native_path_reaches_the_caller_as_other() -> None:
    _, stop_reason = send(ExpenseClaim, "refusal", "I can't help with that.")
    assert stop_reason == "other"  # create() returns it; nothing raised before our code


def test_why_the_adapter_does_not_use_parse() -> None:
    # messages.parse() validates the text itself, so a refusal raises before any stop
    # reason can be read. The adapter calls create() and leaves validation to extract().
    http = anthropic.DefaultHttpxClient(
        transport=httpx2.MockTransport(lambda _: reply("refusal", "I can't help with that."))
    )
    client = anthropic.Anthropic(api_key="test-key", max_retries=0, http_client=http)
    with pytest.raises(ValidationError):
        client.messages.parse(
            model="test-model", max_tokens=400, messages=[{"role": "user", "content": "hi"}],
            output_format=ExpenseClaim,
        )  # fmt: skip


def test_the_timeout_keeps_a_short_connect_limit() -> None:
    timeout = AnthropicAdapter(SETTINGS)._client.timeout
    assert isinstance(timeout, httpx2.Timeout)
    assert (timeout.connect, timeout.read) == (5.0, SETTINGS.timeout_seconds)
