"""Calls the real provider. Skipped by default; run with `uv run --env-file .env pytest -m live`."""

import os

import pytest
from ch09.agent import run_agent
from ch09.anthropic_adapter import AnthropicAdapter
from ch09.budget import CallLimits, RunBudget, StopCause
from ch09.context_budget import context_budget_from
from ch09.doc_tools import build_doc_registry
from ch09.inspector import ContextInspector
from ch09.prompts import load_prompt
from ch09.questions import QUESTIONS
from ch09.settings import Settings
from kestrel.workspace import copy_docs

pytestmark = pytest.mark.live


def test_live_docs_run_counts_with_the_provider_and_ends_with_a_named_cause(tmp_path):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("needs ANTHROPIC_API_KEY and MODEL")
    copy_docs(tmp_path / "docs")
    settings = Settings.from_env()
    client = AnthropicAdapter(settings)
    context = context_budget_from(settings)
    result = run_agent(
        client,
        load_prompt("docs_agent", 1).body,
        QUESTIONS[0].question,
        build_doc_registry(tmp_path / "docs", context.tool_result_max_chars),
        RunBudget(settings.run_max_steps, settings.run_max_tokens, settings.run_max_seconds),
        CallLimits(settings.max_output_tokens, settings.timeout_seconds),
        inspector=ContextInspector(client, context),
    )
    assert result.cause in set(StopCause)
    assert all(s.context is None or s.context.provider_counts for s in result.steps)
