"""Calls the real provider. Skipped by default; run with `uv run --env-file .env pytest -m live`."""

import os

import httpx
import pytest
from ch07.agent import run_agent
from ch07.anthropic_adapter import AnthropicAdapter
from ch07.budget import CallLimits, RunBudget, StopCause
from ch07.ops_agent import question_for
from ch07.prompts import load_prompt
from ch07.settings import Settings
from ch07.tools import build_registry

pytestmark = pytest.mark.live


def test_live_run_ends_with_a_named_cause(kestrel_url):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and MODEL")
    settings = Settings.from_env()
    budget = RunBudget(settings.run_max_steps, settings.run_max_tokens, settings.run_max_seconds)
    limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        result = run_agent(
            AnthropicAdapter(settings),
            load_prompt("ops_agent", 1).body,
            question_for(["O-0014614", "O-9999999"]),
            build_registry(http),
            budget,
            limits,
        )
    assert result.cause in set(StopCause)
    assert len(result.steps) <= budget.max_steps
