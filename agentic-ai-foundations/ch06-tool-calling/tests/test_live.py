"""Calls the real provider. Skipped by default; run with `uv run --env-file .env pytest -m live`."""

import os

import httpx
import pytest
from ch06.anthropic_adapter import AnthropicAdapter
from ch06.prompts import load_prompt
from ch06.round_trip import run_round_trip
from ch06.settings import Settings
from ch06.tools import build_registry

pytestmark = pytest.mark.live


def test_one_round_trip_answers_from_the_tool(kestrel_url):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and MODEL")
    settings = Settings.from_env()
    client = AnthropicAdapter(settings)
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        final = run_round_trip(
            client,
            build_registry(http),
            load_prompt("order_lookup", 1).body,
            "Is order O-0000141 still open?",
            settings.max_output_tokens,
        )
    assert final.stop_reason in ("finished", "tool_call")
