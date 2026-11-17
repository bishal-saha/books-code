"""The graders on hand-written traces: each failure comes back with a reason."""

from ch13.golden import load_golden_tasks
from ch13.grading import grade

TASKS = {t.id: t for t in load_golden_tasks()}


def trace(output: str, calls: list[tuple[str, dict]], cause: str = "finished") -> list[dict]:
    events = [{"kind": "tool_call", "tool": name, "args": args} for name, args in calls]
    return [*events, {"kind": "run_end", "stop_cause": cause, "output": output}]


def reasons(task_id: str, events: list[dict]) -> list[str]:
    return [c.reason for c in grade(TASKS[task_id], events) if not c.passed]


STOCK_CALL = ("get_stock", {"sku": "SKU-00042"})
STOCK_OK = '{"sku": "SKU-00042", "total_on_hand": 198}'


def test_a_correct_run_passes_every_check():
    assert reasons("stock-total", trace(STOCK_OK, [STOCK_CALL])) == []


def test_a_forbidden_call_fails_even_with_the_right_answer():
    events = trace(STOCK_OK, [STOCK_CALL, ("get_ticket", {"ticket_id": "T-000042"})])
    assert reasons("stock-total", events) == ["forbidden call: get_ticket"]


def test_a_right_answer_without_the_lookup_fails():
    assert reasons("stock-total", trace(STOCK_OK, [])) == [
        "missing call: get_stock {'sku': 'SKU-00042'}"
    ]


def test_json_in_a_code_fence_fails_the_schema():
    fenced = f"```json\n{STOCK_OK}\n```"
    assert reasons("stock-total", trace(fenced, [STOCK_CALL])) == [
        "StockTotal: 1 error(s)",
        "missing fact: total_on_hand=198",
    ]


def test_a_partial_run_reports_only_its_stop_cause():
    assert reasons("stock-total", trace("", [STOCK_CALL] * 4, cause="step_limit")) == [
        "stopped by step_limit"
    ]
