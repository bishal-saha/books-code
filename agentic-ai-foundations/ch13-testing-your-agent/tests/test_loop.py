"""The loop with the fake model: a normal run, and a tool error that becomes a result."""

from ch13.agent import run_agent
from ch13.budget import CallLimits, RunBudget, StopCause
from ch13.fake_model import FakeModelClient
from ch13.scripted import finished, tool_use

BUDGET = RunBudget(max_steps=5, max_total_tokens=60_000, max_wall_seconds=90)
LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30)


def test_one_tool_call_then_finished(registry):
    model = FakeModelClient(
        [
            tool_use("get_order", {"order_id": "O-0000042"}),
            finished('{"order_id": "O-0000042", "status": "delivered"}'),
        ]
    )
    result = run_agent(model, "system", "Status of O-0000042?", registry, BUDGET, LIMITS)

    assert result.cause is StopCause.FINISHED
    assert len(result.steps) == 2
    assert '"delivered"' in model.calls[1].messages[-1].tool_results[0].content


def test_tool_error_is_returned_not_raised(registry):
    model = FakeModelClient(
        [
            tool_use("get_order", {"order_id": "O-9999999"}),
            finished("NEEDS INFO: there is no order O-9999999."),
        ]
    )
    result = run_agent(model, "system", "Status of O-9999999?", registry, BUDGET, LIMITS)

    assert result.steps[0].tool_calls[0].is_error is True
    assert result.cause is StopCause.FINISHED  # the loop carried on after the error
