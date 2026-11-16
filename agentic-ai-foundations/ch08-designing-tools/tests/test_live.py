"""Calls the real provider. Skipped by default; run with `uv run --env-file .env pytest -m live`."""

import os

import pytest
from ch08.budget import CallLimits, RunBudget
from ch08.lookups import kestrel_client
from ch08.return_store import ReturnStore
from ch08.selection_check import run_check
from ch08.settings import Settings

pytestmark = pytest.mark.live


def test_live_selection_check_runs(kestrel_url, tmp_path):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and MODEL")
    from ch08.anthropic_adapter import AnthropicAdapter

    settings = Settings.from_env()
    budget = RunBudget(settings.run_max_steps, settings.run_max_tokens, settings.run_max_seconds)
    limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
    with kestrel_client(kestrel_url) as http:
        reports = run_check(
            AnthropicAdapter(settings), http, ReturnStore(str(tmp_path / "r.sqlite")), 1,
            budget, limits,
        )  # fmt: skip
    assert [r.name for r in reports] == ["v1", "v2"]
    assert all(r.attempts > 0 for r in reports)
