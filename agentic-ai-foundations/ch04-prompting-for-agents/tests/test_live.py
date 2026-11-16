"""Calls the real provider. Skipped by default; run with `uv run pytest -m live` and a key."""

import os

import httpx
import pytest
from ch04.compare import compare, needs_info
from ch04.model_client import build_client
from ch04.prompt_builder import load_prompt
from ch04.settings import Settings

pytestmark = pytest.mark.live


def test_v2_marks_the_missing_order(kestrel_url):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and MODEL")
    settings = Settings.from_env()
    prompt = load_prompt("support_reply", 2)
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        rows = compare(build_client(settings), http, (prompt, prompt),
                       [("T-000007", "missing order")], settings.max_output_tokens)  # fmt: skip
    draft = rows[0].cells[2].draft
    assert draft is not None and needs_info(draft.text)
