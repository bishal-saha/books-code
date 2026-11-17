"""The inspector: shares, headroom, ceilings, counts per run, estimates flagged."""

import pytest
from ch09.agent import run_agent
from ch09.budget import CallLimits, RunBudget
from ch09.context_budget import ContextBudget
from ch09.fake_model import FakeModelClient
from ch09.inspector import (
    ContextInspector,
    blank_tool_results,
    count_fixed,
    inspect_request,
)
from ch09.model_client import (
    Message,
    ModelError,
    ModelResponse,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from ch09.registry import Tool, ToolRegistry
from pydantic import BaseModel, Field


class OrderIdArgs(BaseModel):  # in-memory tools: the loop is under test, not Kestrel
    order_id: str = Field(pattern=r"^O-\d{7}$")


BUDGET = ContextBudget(window=10_000, output_reserve=1_000, tool_result_max_chars=4_000,
                       system_ceiling=50, tools_ceiling=500)  # fmt: skip
TOOL = ToolDefinition(name="get_order", description="Get one order.",
                      input_schema=OrderIdArgs.model_json_schema())  # fmt: skip
CALL = ToolCall(id="call_1", name="get_order", arguments={"order_id": "O-0000001"})
MESSAGES = [
    Message(role="user", content="Where is O-0000001?"),
    Message(role="assistant", tool_calls=[CALL]),
    Message(role="user", tool_results=[ToolResult(tool_call_id="call_1", content="r" * 800)]),
]


def report(system: str = "You are an operations analyst."):
    fake = FakeModelClient([])
    fixed = count_fixed(fake, system, [TOOL])
    return inspect_request(fake, system, [TOOL], MESSAGES, fixed, BUDGET)


def test_shares_sum_to_one_and_components_add_up_to_the_total():
    r = report()
    assert sum(c.tokens for c in r.components) == r.total_input
    assert sum(c.share for c in r.components) == pytest.approx(1.0)
    assert r.tokens("tool_results") == 200  # 800 chars at the fake's 4 chars per token


def test_headroom_accounts_for_the_output_reserve():
    r = report()
    assert r.headroom == 10_000 - r.total_input - 1_000


def test_a_component_over_its_ceiling_is_flagged():
    r = report(system="s" * 400)  # 100 tokens against a ceiling of 50
    flags = {c.name: c.over for c in r.components}
    assert flags["system"] and not flags["tools"]


def test_estimates_are_labelled_as_estimates():
    assert report().provider_counts is False


def test_blanking_keeps_every_tool_result_paired_with_its_call():
    blanked = blank_tool_results(MESSAGES)
    (result,) = blanked[2].tool_results
    assert (result.tool_call_id, result.content) == ("call_1", "")
    assert MESSAGES[2].tool_results[0].content == "r" * 800  # the original is untouched


def scripted_run(fake: FakeModelClient, steps: int = 3):
    registry = ToolRegistry(max_result_chars=4_000)
    registry.register(Tool("get_order", "Get one order.", OrderIdArgs,
                           lambda a: {"order_id": a.order_id, "status": "shipped"}))  # fmt: skip
    return run_agent(fake, "sys", "Where is O-0000001?", registry,
                     RunBudget(8, 50_000, 60.0), CallLimits(1_000, 30.0),
                     inspector=ContextInspector(fake, BUDGET))  # fmt: skip


def tool_step(n: int) -> ModelResponse:
    call = ToolCall(id=f"call_{n}", name="get_order", arguments={"order_id": "O-0000001"})
    return ModelResponse(text="", stop_reason="tool_call", usage=Usage(input_tokens=10,
                         output_tokens=5), tool_calls=[call])  # fmt: skip


def test_fixed_counts_are_made_once_per_run_then_two_counts_per_step():
    fake = FakeModelClient([tool_step(1), tool_step(2), "done"])
    result = scripted_run(fake)
    assert len(result.steps) == 3 and all(s.context for s in result.steps)
    assert fake.count_calls == 3 + 2 * 3
    shares = [s.context.tokens("tool_results") for s in result.steps]
    assert shares[0] == 0 and shares[0] < shares[1] < shares[2]  # results pile up


class FailingCounts(FakeModelClient):
    def count_tokens(self, *args, **kwargs) -> int:
        raise ModelError("timeout", "count timed out")


def test_a_failed_count_is_skipped_and_the_run_goes_on():
    result = scripted_run(FailingCounts(["done"]))
    assert result.cause == "finished" and result.steps[0].context is None


def test_measuring_shrinks_the_model_calls_timeout():
    ticks = iter(range(0, 1000, 10))  # every clock read moves on 10 s
    fake = FakeModelClient(["done"])
    registry = ToolRegistry(max_result_chars=4_000)
    result = run_agent(fake, "sys", "q", registry, RunBudget(8, 50_000, 60.0),
                       CallLimits(1_000, 30.0), clock=lambda: next(ticks),
                       inspector=ContextInspector(fake, BUDGET))  # fmt: skip
    assert result.cause == "finished"
    assert fake.calls[0].timeout < 30.0  # the time spent counting came off this call
