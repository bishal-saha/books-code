"""The recorder: what a trace holds, that the grader can read it, that runs never share a file."""

from pathlib import Path

import pytest
from ch13.agent import run_agent
from ch13.budget import CallLimits, RunBudget
from ch13.fake_model import FakeModelClient
from ch13.golden import load_golden_tasks
from ch13.grading import grade
from ch13.scripted import ILLUSTRATIVE, finished, tool_use
from ch13.trace import TraceRecorder, read_trace

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "traces"
BUDGET = RunBudget(max_steps=4, max_total_tokens=60_000, max_wall_seconds=90)
LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30)


def golden(task_id: str):
    return next(t for t in load_golden_tasks() if t.id == task_id)


def test_recorded_trace_can_be_graded(registry, tmp_path):
    model = FakeModelClient(
        [
            tool_use("get_order", {"order_id": "O-9999999"}),
            finished("NEEDS INFO: there is no order O-9999999."),
        ]
    )
    path = tmp_path / "run.jsonl"
    with TraceRecorder(path, ILLUSTRATIVE) as rec:
        rec.run_start("t1", "unknown-order-needs-info", "operations_v1", "fake", BUDGET)
        run_agent(model, "system", "Where is O-9999999?", registry, BUDGET, LIMITS, recorder=rec)

    events = read_trace(path)
    assert [e["kind"] for e in events] == [
        "run_start",
        "model_call",
        "tool_call",
        "model_call",
        "run_end",
    ]
    assert events[2]["is_error"] is True
    assert events[-1]["cost_usd"] == pytest.approx(0.00275)  # illustrative price
    assert all(c.passed for c in grade(golden("unknown-order-needs-info"), events))


def test_second_run_to_same_path_is_refused(tmp_path):
    path = tmp_path / "run.jsonl"
    with TraceRecorder(path, ILLUSTRATIVE):
        pass
    with pytest.raises(FileExistsError), TraceRecorder(path, ILLUSTRATIVE):
        pass


def test_a_crashed_run_still_grades_as_a_failure(tmp_path):
    path = tmp_path / "run.jsonl"
    with TraceRecorder(path, ILLUSTRATIVE) as rec:
        rec.run_start("t1", "order-status", "operations_v1", "fake", BUDGET)  # then nothing
    checks = grade(golden("order-status"), read_trace(path))
    assert [c.reason for c in checks] == ["no run_end: the run did not complete"]


def test_sample_traces_show_the_failures_the_chapter_reads():
    carrier = read_trace(FIXTURES / "wrong_carrier.jsonl")
    shipments = next(e for e in carrier if e["kind"] == "tool_call")
    assert shipments["args"] == {"late": True, "limit": 20}
    assert shipments["content"].count('"shipment_id"') == 20  # a full page: more rows exist
    failed = [c.reason for c in grade(golden("late-top-carrier-needs-info"), carrier) if c.reason]
    assert failed == ["missing fact: NEEDS INFO"]

    stock = read_trace(FIXTURES / "wrong_stock.jsonl")
    failed = [c.reason for c in grade(golden("stock-total"), stock) if c.reason]
    assert failed == ["missing fact: total_on_hand=198"]
