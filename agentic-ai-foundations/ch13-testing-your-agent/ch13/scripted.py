"""Fake-model scripts for the tests and for `python -m ch13.eval` without --live.

Everything the "model" says here is written by hand: tool calls, answers and token counts are
fake-model output. Tool results are real: the registry calls the seeded Kestrel mock API.
"""

import itertools
from datetime import date
from decimal import Decimal

from ch13.configs import Price
from ch13.fake_model import FakeModelClient
from ch13.golden import GoldenTask
from ch13.model_client import ModelResponse, ToolCall, Usage

ILLUSTRATIVE = Price(
    input_per_mtok=Decimal("1.00"),
    output_per_mtok=Decimal("5.00"),
    as_of=date(2026, 11, 16),
    source_url="illustrative price for the fake model, not a real seller's",
)

_call_ids = itertools.count(1)


def tool_use(name: str, args: dict, *, input_tokens: int = 900, output_tokens: int = 60):
    """A scripted response that requests one tool call, with a unique call id."""
    call = ToolCall(id=f"call_fake_{next(_call_ids)}", name=name, arguments=args)
    usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
    return ModelResponse(text="", stop_reason="tool_call", usage=usage, tool_calls=[call])


def finished(text: str, *, input_tokens: int = 1_300, output_tokens: int = 50) -> ModelResponse:
    """A scripted final answer."""
    usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
    return ModelResponse(text=text, stop_reason="finished", usage=usage)


def never_stops(name: str, args: dict, n: int = 50) -> list[ModelResponse]:
    """A script that asks for a tool on every step and never ends its turn."""
    return [tool_use(name, args) for _ in range(n)]


class FakeClock:
    """Returns start, start + step, start + 2*step, ... on successive calls."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self.now, self.step = start, step

    def __call__(self) -> float:
        value, self.now = self.now, self.now + self.step
        return value


CAPPED_GUESS = '{"carrier": "Harbour Express", "late_shipments": 7}'  # counted from 20 rows
CAP_NOTICE = (
    "NEEDS INFO: list_shipments returns at most 20 rows, so it cannot give a full count "
    "of late shipments per carrier."
)


def passing_script(task_id: str) -> list[ModelResponse]:
    match task_id:
        case "order-status":
            return [
                tool_use("get_order", {"order_id": "O-0000042"}),
                finished('{"order_id": "O-0000042", "status": "delivered"}'),
            ]
        case "shipment-late":
            return [
                tool_use("get_shipment", {"order_id": "O-0000107"}),
                finished('{"order_id": "O-0000107", "carrier": "Swiftway Parcel", "late": false}'),
            ]
        case "stock-total":
            return [
                tool_use("get_stock", {"sku": "SKU-00042"}),
                finished('{"sku": "SKU-00042", "total_on_hand": 198}'),
            ]
        case "ticket-order":
            return [
                tool_use("get_ticket", {"ticket_id": "T-000042"}),
                finished(
                    '{"ticket_id": "T-000042", "order_id": "O-0016227", "priority": "normal"}'
                ),
            ]
        case "unknown-order-needs-info":
            return [
                tool_use("get_order", {"order_id": "O-9999999"}),
                finished("NEEDS INFO: there is no order O-9999999."),
            ]
        case "late-top-carrier-needs-info":
            return [
                tool_use("list_shipments", {"late": True, "limit": 20}),
                finished(CAP_NOTICE),
            ]
    raise KeyError(f"no fake script for task {task_id!r}")


def failing_script(task_id: str) -> list[ModelResponse] | None:
    """The scripted failures: the capped-count guess and a run that never stops."""
    if task_id == "late-top-carrier-needs-info":
        return [tool_use("list_shipments", {"late": True, "limit": 20}), finished(CAPPED_GUESS)]
    if task_id == "stock-total":
        return never_stops("get_stock", {"sku": "SKU-00042"})
    return None


FAILING_TRIALS = {"late-top-carrier-needs-info": {2, 4}, "stock-total": {3}}


def fake_client_for(task: GoldenTask, trial: int) -> FakeModelClient:
    """A fresh fake model for every trial: nothing carries over between runs."""
    if trial in FAILING_TRIALS.get(task.id, set()):
        script = failing_script(task.id)
        assert script is not None
        return FakeModelClient(script)
    return FakeModelClient(passing_script(task.id))


def wrong_stock_script() -> list[ModelResponse]:
    """Exercise 2's run: reads both warehouses, reports one of them as the total."""
    return [
        tool_use("get_stock", {"sku": "SKU-00042"}),
        finished('{"sku": "SKU-00042", "total_on_hand": 118}'),
    ]
