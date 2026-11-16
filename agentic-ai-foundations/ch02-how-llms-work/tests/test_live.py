"""Calls the real provider. Skipped by default; run with `uv run pytest -m live` and a key."""

import os

import pytest
from ch02.settings import Settings
from ch02.tokens import count_text, load_page

pytestmark = pytest.mark.live


def test_count_tokens_against_the_provider():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and the settings in .env")
    settings = Settings.from_env()
    page = load_page(settings, "returns-policy.md")
    result = count_text(settings, "returns-policy.md", page)
    assert result.counted_tokens is not None and result.counted_tokens > 0
