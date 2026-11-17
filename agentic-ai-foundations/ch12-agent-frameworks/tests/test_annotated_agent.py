"""The annotated loop still behaves like Chapter 8's: every exit, errors as results."""

from collections.abc import Sequence

import pytest
from ch12.annotated_agent import run_agent
from ch12.budget import CallLimits, RunBudget, StopCause
from ch12.fake_model import FakeModelClient, ScriptItem
from ch12.model_client import ModelError, ModelResponse, ToolCall, Usage
from ch12.registry import Tool, ToolError, ToolRegistry
from pydantic import BaseModel

BUDGET = RunBudget(max_steps=4, max_total_tokens=10_000, max_wall_seconds=60.0)
LIMITS = CallLimits(max_output_tokens=1_024, timeout_seconds=30.0)


class OrderArgs(BaseModel):
    order_id: str


def lookup(args: OrderArgs) -> dict:
    if args.order_id == "O-0000999":
        raise ToolError(f"No order {args.order_id}.")
    return {"order_id": args.order_id, "status": "shipped"}


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(Tool("get_order", "Get one order.", OrderArgs, lookup))
    return r


def ask(name: str = "get_order", order_id: str = "O-0000042", tokens: int = 100):
    call = ToolCall(id="call_1", name=name, arguments={"order_id": order_id})
    usage = Usage(input_tokens=tokens, output_tokens=tokens // 4)
    return ModelResponse(text="", stop_reason="tool_call", usage=usage, tool_calls=[call])


def run(script: Sequence[ScriptItem], registry: ToolRegistry, budget: RunBudget = BUDGET):
    client = FakeModelClient(script)
    return run_agent(client, "system", "question", registry, budget, LIMITS), client


def test_finishes_after_a_tool_call(registry):
    result, _ = run([ask(), "Order O-0000042 is shipped."], registry)
    assert result.cause is StopCause.FINISHED
    assert result.final_text == "Order O-0000042 is shipped."
    assert [len(s.tool_calls) for s in result.steps] == [1, 0]


def test_a_model_that_never_ends_stops_at_the_step_limit(registry):
    result, _ = run([ask()] * 10, registry)
    assert result.cause is StopCause.STEP_LIMIT
    assert result.final_text == ""  # a partial result, never an answer
    assert len(result.steps) == BUDGET.max_steps


def test_token_limit_is_checked_before_the_next_call(registry):
    budget = RunBudget(max_steps=10, max_total_tokens=1_000, max_wall_seconds=60.0)
    result, client = run([ask(tokens=480)] * 5, registry, budget)
    assert result.cause is StopCause.TOKEN_LIMIT
    assert len(client.calls) == 2  # no third call once the budget is spent
    assert client.calls[1].max_tokens == 1_000 - 600  # output capped to what was left
    assert result.total_tokens == 1_200  # input is known only after the call: overshoot


@pytest.mark.parametrize(
    ("name", "order_id"), [("track_parcel", "O-0000042"), ("get_order", "O-0000999")]
)
def test_unknown_tools_and_tool_errors_come_back_as_results(registry, name, order_id):
    result, _ = run([ask(name, order_id), "Done."], registry)
    assert result.cause is StopCause.FINISHED  # the run did not raise
    assert result.steps[0].tool_calls[0].is_error
    assert result.messages[2].tool_results[0].is_error


def test_a_failed_model_call_is_a_stop_cause(registry):
    result, _ = run([ModelError("timeout", "timed out")], registry)
    assert result.cause is StopCause.MODEL_ERROR
