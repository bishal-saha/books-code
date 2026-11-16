"""run_agent on scripted fake-model runs: every exit, the step log, tool errors as results."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from ch07.agent import RunResult, run_agent
from ch07.budget import CallLimits, RunBudget, StopCause
from ch07.fake_model import FakeModelClient
from ch07.model_client import (
    ModelClient,
    ModelError,
    ModelResponse,
    StopReason,
    ToolCall,
    Usage,
)
from ch07.tools import OrderIdArgs, Tool, ToolError, ToolRegistry

BUDGET = RunBudget(max_steps=5, max_total_tokens=10_000, max_wall_seconds=60.0)
LIMITS = CallLimits(max_output_tokens=1_024, timeout_seconds=30.0)


def lookup(args: OrderIdArgs) -> dict:
    if args.order_id == "O-0000999":
        raise ToolError(f"No order {args.order_id} exists.")
    return {"order_id": args.order_id, "status": "shipped"}


def slow(args: OrderIdArgs) -> dict:
    raise httpx.ReadTimeout("read timed out")


@pytest.fixture
def registry() -> ToolRegistry:
    """In-memory tools: the loop is under test here, not the Kestrel API."""
    r = ToolRegistry()
    r.register(Tool("get_order", "Get one order.", OrderIdArgs, lookup))
    r.register(Tool("get_shipment", "Get one shipment (always times out).", OrderIdArgs, slow))
    return r


def calls(*order_ids: str, name: str = "get_order") -> list[ToolCall]:
    return [
        ToolCall(id=f"call_{i}", name=name, arguments={"order_id": o})
        for i, o in enumerate(order_ids, 1)
    ]


def respond(
    tool_calls: Sequence[ToolCall] = (),
    text: str = "",
    stop: StopReason = "tool_call",
    tokens: int = 100,  # input tokens; output is a quarter of it
) -> ModelResponse:
    usage = Usage(input_tokens=tokens, output_tokens=tokens // 4)
    return ModelResponse(text=text, stop_reason=stop, usage=usage, tool_calls=list(tool_calls))


def done(text: str = "Done.") -> ModelResponse:
    return respond(text=text, stop="finished")


def ask(
    client: ModelClient, registry: ToolRegistry, budget: RunBudget = BUDGET, **kwargs: Any
) -> RunResult:
    return run_agent(client, "You are an operations analyst.", "Where is O-0000042?",
                     registry, budget, LIMITS, **kwargs)  # fmt: skip


def test_tool_step_then_finished(registry):
    fake = FakeModelClient([respond(calls("O-0000042")), done("O-0000042 has shipped.")])
    result = ask(fake, registry)

    assert result.cause is StopCause.FINISHED
    assert result.final_text == "O-0000042 has shipped."
    sent = fake.calls[1].messages  # what the second model call received
    assert [m.role for m in sent] == ["user", "assistant", "user"]
    assert sent[1].tool_calls[0].id == "call_1"  # the tool call first
    assert sent[2].tool_results[0].tool_call_id == "call_1"  # then its result


def test_step_log_records_each_step(registry):
    fake = FakeModelClient([respond(calls("O-0000042", "O-0000999")), done()])
    first, second = ask(fake, registry).steps

    assert (first.messages_sent, first.max_output_tokens, first.timeout_seconds) == (1, 1024, 30.0)
    assert (first.stop_reason, first.input_tokens, first.output_tokens) == ("tool_call", 100, 25)
    assert [(c.name, c.arguments, c.is_error) for c in first.tool_calls] == [
        ("get_order", {"order_id": "O-0000042"}, False),
        ("get_order", {"order_id": "O-0000999"}, True),
    ]
    assert first.tool_calls[1].result_preview == "No order O-0000999 exists."
    assert (second.messages_sent, second.stop_reason, second.tool_calls) == (3, "finished", [])


def test_model_that_never_stops_hits_the_step_limit(registry):
    script = [respond(calls("O-0000042")) for _ in range(BUDGET.max_steps)]
    result = ask(FakeModelClient(script), registry)

    assert result.cause is StopCause.STEP_LIMIT
    assert len(result.steps) == BUDGET.max_steps
    assert result.final_text == ""  # a stopped run has no answer


def test_token_limit(registry):
    script = [respond(calls("O-0000042"), tokens=4_000) for _ in range(BUDGET.max_steps)]
    result = ask(FakeModelClient(script), registry)

    assert result.cause is StopCause.TOKEN_LIMIT
    assert len(result.steps) == 2  # 5,000 tokens per step: no room left for a third
    assert result.total_tokens == 10_000


@dataclass
class FakeClock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


class SlowModel:
    """Wraps the fake so every model call 'takes' 40 seconds of fake time."""

    def __init__(self, inner: FakeModelClient, clock: FakeClock) -> None:
        self.inner, self.clock = inner, clock

    def complete(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self.clock.now += 40.0
        return self.inner.complete(*args, **kwargs)


def test_time_limit_and_the_shrinking_timeout(registry):
    clock = FakeClock()
    fake = FakeModelClient([respond(calls("O-0000042")) for _ in range(5)])
    result = ask(SlowModel(fake, clock), registry, clock=clock)

    assert result.cause is StopCause.TIME_LIMIT
    assert len(result.steps) == 2  # 40 s + 40 s = 80 s, over the 60 s budget
    assert [c.timeout for c in fake.calls] == [30.0, 20.0]  # 60 s budget - 40 s used


def test_no_call_when_too_little_time_is_left(registry):
    fake = FakeModelClient([])  # any model call would fail the test
    tight = RunBudget(max_steps=5, max_total_tokens=10_000, max_wall_seconds=0.5)
    result = ask(fake, registry, tight, clock=FakeClock())

    assert result.cause is StopCause.TIME_LIMIT
    assert result.steps == [] and fake.calls == []


def test_model_error_keeps_earlier_steps(registry):
    fake = FakeModelClient([respond(calls("O-0000042")), ModelError("provider_error", "503")])
    result = ask(fake, registry)

    assert result.cause is StopCause.MODEL_ERROR
    assert len(result.steps) == 1
    assert len(result.messages) == 3  # question, tool call, tool result: all kept


def test_truncated_reply_is_not_an_answer(registry):
    fake = FakeModelClient([respond(text="O-0000042 has", stop="truncated")])
    result = ask(fake, registry)
    assert result.cause is StopCause.TRUNCATED
    assert result.final_text == "O-0000042 has"  # the fragment, labelled by the cause


def test_truncated_by_the_budget_remainder_is_a_token_limit(registry):
    fake = FakeModelClient([respond(calls("O-0000042"), tokens=7_600), respond(stop="truncated")])
    result = ask(fake, registry)
    assert fake.calls[1].max_tokens == 500  # 10,000 - 9,500 used, below the 1,024 cap
    assert result.cause is StopCause.TOKEN_LIMIT


@pytest.mark.parametrize("response", [respond(stop="other"), respond(text="Checking now.")])
def test_unexpected_stops(registry, response):  # an unknown reason; tool_call with no calls
    assert ask(FakeModelClient([response]), registry).cause is StopCause.UNEXPECTED_STOP


def test_tool_failures_go_back_as_results(registry):
    bad = [
        ToolCall(id="a", name="get_order", arguments={"order_id": "O-0000042"}),
        ToolCall(id="b", name="get_order", arguments={"order_id": "O-0000999"}),  # 404
        ToolCall(id="c", name="get_invoice", arguments={}),  # not a registered tool
        ToolCall(id="d", name="get_order", arguments={"order_id": "42"}),  # invalid
        ToolCall(id="e", name="get_shipment", arguments={"order_id": "O-0000042"}),  # timeout
    ]
    fake = FakeModelClient([respond(bad), done()])
    result = ask(fake, registry)

    assert result.cause is StopCause.FINISHED  # nothing raised, the run went on
    results = fake.calls[1].messages[-1].tool_results  # one message, in call order
    assert [r.tool_call_id for r in results] == ["a", "b", "c", "d", "e"]
    assert [r.is_error for r in results] == [False, True, True, True, True]
    assert results[2].content.startswith("Unknown tool: get_invoice.")
    assert results[4].content.startswith("get_shipment timed out. Retry once")
