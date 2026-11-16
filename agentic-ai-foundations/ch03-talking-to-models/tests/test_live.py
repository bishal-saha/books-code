"""Calls the real provider. Skipped by default; run with `uv run --env-file .env pytest -m live`."""

import os

import pytest
from ch03.model_client import Message, build_client
from ch03.settings import Settings
from ch03.ticket_prompt import SYSTEM_PROMPT

pytestmark = pytest.mark.live


@pytest.fixture
def client_and_settings():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and the settings in .env")
    settings = Settings.from_env()
    return build_client(settings), settings


def test_complete_returns_text_usage_and_a_request_id(client_and_settings):
    client, _ = client_and_settings
    response = client.complete(SYSTEM_PROMPT, [Message(role="user", content="Say hello.")], 50)
    assert response.text and response.usage.output_tokens > 0
    assert response.request_id


def test_a_tiny_cap_truncates(client_and_settings):
    client, _ = client_and_settings
    ask = [Message(role="user", content="Write three paragraphs about tents.")]
    assert client.complete(SYSTEM_PROMPT, ask, 5).stop_reason == "truncated"


def test_stream_ends_with_one_response(client_and_settings):
    client, _ = client_and_settings
    items = list(client.stream(SYSTEM_PROMPT, [Message(role="user", content="Say hello.")], 50))
    assert all(isinstance(i, str) for i in items[:-1])
    assert items[-1].stop_reason == "finished"
