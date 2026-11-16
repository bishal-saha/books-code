"""The scripted runs end to end: fake model, real tools against the seeded Kestrel API."""

import json

import httpx
from ch07.agent import print_steps, run_agent
from ch07.budget import StopCause
from ch07.ops_agent import FAKE_BUDGET, FAKE_LIMITS, question_for
from ch07.prompts import load_prompt
from ch07.scripted import CHASED, chased, stuck
from ch07.tools import build_registry


def run(client, kestrel_url):
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        return run_agent(client, load_prompt("ops_agent", 1).body, question_for(CHASED),
                         build_registry(http), FAKE_BUDGET, FAKE_LIMITS)  # fmt: skip


def test_chased_orders_run(kestrel_url):
    result = run(chased(), kestrel_url)
    assert result.cause is StopCause.FINISHED
    assert [len(s.tool_calls) for s in result.steps] == [4, 2, 1, 0]
    errors = [c.result_preview for s in result.steps for c in s.tool_calls if c.is_error]
    assert errors == ["No order O-9999999 exists."]


def test_the_scripted_answer_matches_the_real_tool_results(kestrel_url):
    result = run(chased(), kestrel_url)
    shipments = result.messages[4].tool_results  # step 2's results
    lost, in_transit = (json.loads(r.content[6:-7]) for r in shipments)  # strip <data> tags
    assert (lost["carrier"], lost["status"], lost["late"]) == ("Northline Freight", "lost", True)
    assert (in_transit["carrier"], in_transit["status"]) == ("Swiftway Parcel", "in_transit")
    listed = json.loads(result.messages[6].tool_results[0].content[6:-7])
    assert len(listed) == 10 and all(s["status"] == "delivered" and s["late"] for s in listed)


def test_stuck_model_is_stopped_by_the_step_limit(kestrel_url):
    lines: list[str] = []
    result = run(stuck(), kestrel_url)
    print_steps(result, FAKE_BUDGET, out=lines.append)
    assert result.cause is StopCause.STEP_LIMIT
    assert len(result.steps) == FAKE_BUDGET.max_steps
    assert lines[-1].startswith("stopped: step_limit  steps 8/8  tokens 7520/60000")
