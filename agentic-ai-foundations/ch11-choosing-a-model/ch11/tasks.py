"""Six Kestrel tasks with checkable answers, and the one place that defines success.

Every expected value is computed from the mock API when the check runs, so nothing here
hard-codes a status, a stock level or a policy number.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ch11.agent import RunResult
from ch11.budget import StopCause

# --- Answer shapes: every task answers with one JSON object ---


class OrderStatus(BaseModel):
    order_id: str
    status: str


class LateCount(BaseModel):
    carrier: str
    late_shipments: int


class MostStock(BaseModel):
    sku: str
    total_on_hand: int


class TicketTriage(BaseModel):
    ticket_id: str
    order_id: str
    priority: str
    status: str


class DeliveryPromise(BaseModel):
    standard_delivery_working_days: int


class ShipmentPolicy(BaseModel):
    order_id: str
    carrier: str
    late: bool
    carrier_in_current_policy: bool


# --- Expected values, read from the mock API at check time ---


def _get(api: httpx.Client, path: str) -> Any:
    response = api.get(path)
    response.raise_for_status()
    return response.json()


def current_shipping_policy(api: httpx.Client) -> str:
    return _get(api, "/policies/shipping-policy")["body"]


def expect_order_status(api: httpx.Client) -> dict[str, Any]:
    return {"order_id": "O-0000042", "status": _get(api, "/orders/O-0000042")["status"]}


def expect_late_count(api: httpx.Client) -> dict[str, Any]:
    params = {"carrier": "Tallpine Logistics", "late": "true", "limit": 500}
    rows = _get(api, f"/shipments?{httpx.QueryParams(params)}")
    assert len(rows) < 500, "the count reached the mock's 500-row cap; pick another carrier"
    return {"carrier": "Tallpine Logistics", "late_shipments": len(rows)}


def expect_most_stock(api: httpx.Client) -> dict[str, Any]:
    totals = {
        sku: sum(w["on_hand"] for w in _get(api, f"/stock/{sku}")["warehouses"])
        for sku in ("SKU-00042", "SKU-00043")
    }
    sku = max(totals, key=totals.__getitem__)
    return {"sku": sku, "total_on_hand": totals[sku]}


def expect_ticket(api: httpx.Client) -> dict[str, Any]:
    t = _get(api, "/tickets/T-000042")
    return {k: t[k] for k in ("ticket_id", "order_id", "priority", "status")}


def expect_promise(api: httpx.Client) -> dict[str, Any]:
    days = re.search(r"Standard delivery promise: (\d+) working days", current_shipping_policy(api))
    assert days, "the current shipping policy no longer states a standard promise"
    return {"standard_delivery_working_days": int(days.group(1))}


def expect_shipment_policy(api: httpx.Client) -> dict[str, Any]:
    s = _get(api, "/orders/O-0000107/shipment")
    carriers = re.search(r"Carriers in use[^:]*: (.+?)\.\s", current_shipping_policy(api))
    assert carriers, "the current shipping policy no longer lists its carriers"
    listed = [c.strip() for c in carriers.group(1).split(",")]
    return {
        "order_id": "O-0000107",
        "carrier": s["carrier"],
        "late": s["late"],
        "carrier_in_current_policy": s["carrier"] in listed,
    }


# --- The tasks ---


@dataclass(frozen=True)
class Task:
    task_id: str
    prompt: str
    required_tools: frozenset[str]
    answer: type[BaseModel]  # the JSON shape the final answer must have
    expected: Callable[[httpx.Client], dict[str, Any]]  # field values a correct answer has


TASKS = [
    Task(
        "order-status",
        "What is the status of order O-0000042? Answer as JSON with order_id and status.",
        frozenset({"get_delivery_status"}),
        OrderStatus,
        expect_order_status,
    ),
    Task(
        "late-count",
        "How many late Tallpine Logistics shipments are there? Answer as JSON with carrier "
        "and late_shipments.",
        frozenset({"list_shipments"}),
        LateCount,
        expect_late_count,
    ),
    Task(
        "most-stock",
        "Which has more units on hand across both warehouses, SKU-00042 or SKU-00043? "
        "Answer as JSON with sku and total_on_hand for that SKU.",
        frozenset({"get_stock"}),
        MostStock,
        expect_most_stock,
    ),
    Task(
        "ticket-triage",
        "Read ticket T-000042 and answer as JSON with ticket_id, order_id, priority and status.",
        frozenset({"get_ticket"}),
        TicketTriage,
        expect_ticket,
    ),
    Task(
        "outdated-policy",
        "How many working days is Kestrel's standard delivery promise? Answer as JSON with "
        "standard_delivery_working_days.",
        frozenset({"get_policy"}),
        DeliveryPromise,
        expect_promise,
    ),
    Task(
        "shipment-plus-policy",
        "Look up the shipment for order O-0000107. Is its carrier one the current shipping "
        "policy lists, and was it late? Answer as JSON with order_id, carrier, late and "
        "carrier_in_current_policy.",
        frozenset({"get_delivery_status", "get_policy"}),
        ShipmentPolicy,
        expect_shipment_policy,
    ),
]


# --- Success, defined once ---


def tools_called(result: RunResult) -> set[str]:
    return {call.name for step in result.steps for call in step.tool_calls}


def failure_label(task: Task, result: RunResult, api: httpx.Client) -> str | None:
    """None means success; otherwise the label written to the results file."""
    if result.cause is not StopCause.FINISHED:
        return result.cause.value  # step_limit, time_limit, model_error, ...
    if task.required_tools - tools_called(result):
        return "no required tool call"  # a right answer without the lookup is a guess
    try:
        answer = task.answer.model_validate_json(result.final_text)  # strict: no fence stripping
    except ValidationError:
        return "invalid structured output"
    expected = task.expected(api)
    return None if all(getattr(answer, k) == v for k, v in expected.items()) else "wrong answer"
