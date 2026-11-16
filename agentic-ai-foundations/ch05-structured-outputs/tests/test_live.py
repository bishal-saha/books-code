"""Calls the real provider. Skipped by default; run with `uv run pytest -m live` and a key."""

import os

import pytest
from ch05.anthropic_adapter import AnthropicAdapter
from ch05.claims import extract_claim
from ch05.models import ExpenseClaim
from ch05.sample_replies import CLAIM_TEXT, TODAY
from ch05.settings import Settings

pytestmark = pytest.mark.live


@pytest.mark.parametrize("native", [False, True])
def test_claim_01_extracts(native: bool) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and MODEL")
    settings = Settings.from_env()
    client = AnthropicAdapter(settings, output_format=ExpenseClaim if native else None)
    result = extract_claim(
        client, CLAIM_TEXT, max_attempts=settings.max_extraction_attempts,
        max_tokens=settings.max_output_tokens, today=TODAY,
    )  # fmt: skip
    claim = result.value
    assert (claim.category, claim.currency, claim.receipt_attached) == ("meals", "USD", True)
