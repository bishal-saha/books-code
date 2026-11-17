"""The operations agent's scripted run with the inspector on, against the seeded API."""

from datetime import date

from ch09.agent import run_agent
from ch09.inspect_ops import question_for
from ch09.inspector import ContextInspector
from ch09.lookups import kestrel_client
from ch09.prompts import load_prompt
from ch09.return_store import ReturnStore
from ch09.scripted import CHASED, FAKE_BUDGET, FAKE_CONTEXT, FAKE_LIMITS, chased
from ch09.tools import build_registry


def test_tool_results_become_the_largest_component(kestrel_url, tmp_path):
    client = chased()
    with kestrel_client(kestrel_url) as http:
        registry = build_registry(http, ReturnStore(f"{tmp_path}/r.sqlite"), date(2025, 12, 16),
                                  FAKE_CONTEXT.tool_result_max_chars)  # fmt: skip
        result = run_agent(client, load_prompt("ops_agent", 2).body, question_for(CHASED),
                           registry, FAKE_BUDGET, FAKE_LIMITS,
                           inspector=ContextInspector(client, FAKE_CONTEXT))  # fmt: skip
    reports = [s.context for s in result.steps]
    assert result.cause == "finished" and len(reports) == 3
    fixed = {(r.tokens("system"), r.tokens("tools")) for r in reports}
    assert len(fixed) == 1  # system prompt and tool definitions never change mid-run
    last = {c.name: c.tokens for c in reports[-1].components}
    assert last["tool_results"] > last["system"] and last["tool_results"] > last["history"]
