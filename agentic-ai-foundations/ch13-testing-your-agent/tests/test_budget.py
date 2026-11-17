"""Every StopCause other than finished: a labelled partial result plus the step log."""

import pytest
from ch13.agent import run_agent
from ch13.budget import CallLimits, RunBudget, StopCause
from ch13.fake_model import FakeModelClient
from ch13.model_client import ModelError, ModelResponse, Usage
from ch13.scripted import FakeClock, finished, never_stops, tool_use

LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30)
STOCK = ("get_stock", {"sku": "SKU-00042"})


def stopped(reason: str) -> ModelResponse:
    return ModelResponse(text="", stop_reason=reason, usage=Usage(input_tokens=10, output_tokens=5))


CASES = {
    StopCause.STEP_LIMIT: (never_stops(*STOCK), RunBudget(3, 60_000, 90), None),
    StopCause.TOKEN_LIMIT: (
        [tool_use(*STOCK, input_tokens=59_900)],
        RunBudget(5, 60_000, 90),
        None,
    ),
    StopCause.TIME_LIMIT: (never_stops(*STOCK), RunBudget(50, 60_000, 60), FakeClock(step=40.0)),
    StopCause.TRUNCATED: ([stopped("truncated")], RunBudget(5, 60_000, 90), None),
    StopCause.UNEXPECTED_STOP: ([stopped("other")], RunBudget(5, 60_000, 90), None),
    StopCause.MODEL_ERROR: (
        [tool_use(*STOCK), ModelError("timeout", "timed out")],
        RunBudget(5, 60_000, 90),
        None,
    ),
}


@pytest.mark.parametrize("cause", list(CASES), ids=str)
def test_each_stop_cause(cause, registry):
    script, budget, clock = CASES[cause]
    extra = {"clock": clock} if clock else {}
    result = run_agent(
        FakeModelClient(script), "system", "How much SKU-00042?", registry, budget, LIMITS, **extra
    )
    assert result.cause is cause
    assert result.final_text == ""  # only FINISHED carries an answer


def test_time_limit_keeps_what_happened_before_the_stop(registry):
    clock = FakeClock(step=40.0)  # every reading of the clock advances 40 seconds
    budget = RunBudget(max_steps=50, max_total_tokens=60_000, max_wall_seconds=60)
    result = run_agent(
        FakeModelClient(never_stops(*STOCK) + [finished("unused")]),
        "system",
        "How much SKU-00042?",
        registry,
        budget,
        LIMITS,
        clock=clock,
    )
    assert result.cause is StopCause.TIME_LIMIT
    assert result.steps  # the step log is kept
