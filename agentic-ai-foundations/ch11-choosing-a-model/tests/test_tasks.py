"""The six tasks against the seeded mock API, and every branch of failure_label."""

import httpx
import pytest
from ch11.agent import RunResult, StepRecord, ToolCallRecord
from ch11.budget import StopCause
from ch11.model_client import ToolCall
from ch11.tasks import TASKS, failure_label
from ch11.tools import build_registry

TASK = {t.task_id: t for t in TASKS}


@pytest.fixture(scope="module")
def api(kestrel_url: str):
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as client:
        yield client


def finished(text: str, *tools: str, cause: StopCause = StopCause.FINISHED) -> RunResult:
    calls = [ToolCallRecord(name=t, arguments={}, is_error=False, result_preview="") for t in tools]
    step = StepRecord(index=0, messages_sent=1, max_output_tokens=512, timeout_seconds=30.0,
                      stop_reason="finished", tool_calls=calls, input_tokens=1,
                      output_tokens=1, duration_ms=1)  # fmt: skip
    return RunResult(cause=cause, final_text=text, messages=[], steps=[step])


def test_policy_tasks_read_the_current_policy(api) -> None:
    assert TASK["outdated-policy"].expected(api) == {"standard_delivery_working_days": 3}
    expected = TASK["shipment-plus-policy"].expected(api)
    assert expected["carrier"] == "Swiftway Parcel"  # not listed in the outdated v2 policy
    assert expected["carrier_in_current_policy"] is True


def test_every_task_has_an_answerable_expectation(api) -> None:
    for task in TASKS:
        task.answer.model_validate(task.expected(api))


def test_success(api) -> None:
    task = TASK["order-status"]
    answer = '{"order_id": "O-0000042", "status": "delivered"}'
    assert failure_label(task, finished(answer, "get_delivery_status"), api) is None


def test_right_answer_without_the_lookup_fails(api) -> None:
    answer = '{"order_id": "O-0000042", "status": "delivered"}'
    label = failure_label(TASK["order-status"], finished(answer), api)
    assert label == "no required tool call"


def test_fenced_json_is_invalid_structured_output(api) -> None:
    fenced = '```json\n{"order_id": "O-0000042", "status": "delivered"}\n```'
    label = failure_label(TASK["order-status"], finished(fenced, "get_delivery_status"), api)
    assert label == "invalid structured output"


def test_outdated_policy_answer_is_wrong(api) -> None:
    stale = '{"standard_delivery_working_days": 4}'  # the superseded v2 number
    assert failure_label(TASK["outdated-policy"], finished(stale, "get_policy"), api) == (
        "wrong answer"
    )


def test_budget_stop_is_reported_by_its_stop_cause(api) -> None:
    result = finished("", "get_delivery_status", cause=StopCause.STEP_LIMIT)
    assert failure_label(TASK["order-status"], result, api) == "step_limit"


def test_read_only_tools_answer_from_the_api(api) -> None:
    registry = build_registry(api)
    names = [d.name for d in registry.definitions()]
    assert names == ["get_delivery_status", "list_shipments", "get_ticket", "get_policy",
                     "get_stock"]  # fmt: skip
    stock = registry.dispatch(ToolCall(id="1", name="get_stock", arguments={"sku": "SKU-00042"}))
    assert not stock.is_error and "Main (Riverside)" in stock.content
    missing = registry.dispatch(ToolCall(id="2", name="get_policy", arguments={"name": "nope"}))
    assert missing.is_error and "shipping-policy-v2-OUTDATED" in missing.content


def test_registry_rejects_an_invented_parameter(api) -> None:
    call = ToolCall(id="3", name="get_stock", arguments={"sku": "SKU-00042", "warehouse": "x"})
    result = build_registry(api).dispatch(call)
    assert result.is_error and "warehouse: Extra inputs are not permitted" in result.content
