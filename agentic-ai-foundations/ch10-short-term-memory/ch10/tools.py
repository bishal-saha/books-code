"""Chapter 9's tools, registry and dispatcher (results rendered with a provenance header).

New in Chapter 10: get_ticket and get_policy, so Maya's support session can read a ticket and
a Kestrel policy. Everything else is Chapter 9's code, unchanged.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from ch10.model_client import ToolCall, ToolDefinition, ToolResult
from ch10.results import render_tool_result

logger = logging.getLogger(__name__)


# --- The arguments the tools accept: a pydantic model, as in Chapter 5 ---


class OrderIdArgs(BaseModel):  # get_order and get_shipment take one order ID
    order_id: str = Field(
        description="Kestrel order ID, for example O-0000042.", pattern=r"^O-\d{7}$"
    )


class TicketIdArgs(BaseModel):  # new in Chapter 10
    ticket_id: str = Field(
        description="Kestrel ticket ID, for example T-000407.", pattern=r"^T-\d{6}$"
    )


class PolicyArgs(BaseModel):  # new in Chapter 10
    name: str = Field(
        description="Policy name: returns-policy, shipping-policy or expense-policy.",
        pattern=r"^[a-z-]+$",
    )


class ShipmentListArgs(BaseModel):
    carrier: str | None = Field(default=None, description="Carrier name, e.g. Swiftway Parcel.")
    late: bool = Field(default=True, description="True: only late shipments.")
    limit: int = Field(default=10, ge=1, le=20, description="How many shipments to return.")


# --- The functions behind the tools: plain httpx calls to the Kestrel mock API ---


class ToolError(Exception):
    """A tool failure whose message is written to be shown to the model."""


def get_order(http: httpx.Client, args: OrderIdArgs) -> dict[str, Any]:
    response = http.get(f"/orders/{args.order_id}")
    if response.status_code == 404:
        raise ToolError(f"No order {args.order_id} exists.")
    response.raise_for_status()  # anything else unexpected raises; dispatch() reports it
    return response.json()


def get_shipment(http: httpx.Client, args: OrderIdArgs) -> dict[str, Any]:
    response = http.get(f"/orders/{args.order_id}/shipment")
    if response.status_code == 404:
        raise ToolError(f"No shipment for {args.order_id}: {response.json()['error']}.")
    response.raise_for_status()
    return response.json()


def list_shipments(http: httpx.Client, args: ShipmentListArgs) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"late": str(args.late).lower(), "limit": args.limit}
    if args.carrier:
        params["carrier"] = args.carrier
    response = http.get("/shipments", params=params)
    response.raise_for_status()
    return response.json()


def get_ticket(http: httpx.Client, args: TicketIdArgs) -> dict[str, Any]:  # new in Chapter 10
    response = http.get(f"/tickets/{args.ticket_id}")
    if response.status_code == 404:
        raise ToolError(f"No ticket {args.ticket_id} exists.")
    response.raise_for_status()
    return response.json()


def get_policy(http: httpx.Client, args: PolicyArgs) -> str:  # new in Chapter 10
    response = http.get(f"/policies/{args.name}")
    if response.status_code == 404:
        raise ToolError(f"No policy {args.name}. Use returns-policy or shipping-policy.")
    response.raise_for_status()
    return response.json()["body"]


# --- The registry: one record per tool, definitions and dispatch derived from it ---


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    function: Callable[[Any], Any]  # takes the validated args only; bind the rest with partial


class ToolRegistry:
    def __init__(self, max_result_chars: int) -> None:
        self._tools: dict[str, Tool] = {}
        self.max_result_chars = max_result_chars  # the context budget's enforced cap

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                input_schema=t.args_model.model_json_schema(),
            )
            for t in self._tools.values()
        ]

    def dispatch(self, call: ToolCall) -> ToolResult:
        """Run one tool call. Never raises: every outcome is a result carrying call.id."""
        tool = self._tools.get(call.name)
        if tool is None:
            known = ", ".join(self._tools)
            return ToolResult(
                tool_call_id=call.id,
                content=f"Unknown tool: {call.name}. Available tools: {known}.",
                is_error=True,
            )
        try:
            args = tool.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
            )
            return ToolResult(
                tool_call_id=call.id, content=f"Invalid arguments: {problems}", is_error=True
            )
        try:
            output = tool.function(args)
        except ToolError as exc:  # permanent: the same call will fail the same way
            return ToolResult(tool_call_id=call.id, content=str(exc), is_error=True)
        except httpx.TimeoutException:  # transient: the same call may work next time
            return ToolResult(
                tool_call_id=call.id,
                content=f"{tool.name} timed out. Retry once; if it fails again, report it.",
                is_error=True,
            )
        except Exception as exc:  # deliberate: a tool failure becomes a result, not a crash
            logger.exception("tool %s failed for call %s", tool.name, call.id)
            return ToolResult(
                tool_call_id=call.id,
                content=f"{tool.name} failed ({type(exc).__name__}).",
                is_error=True,
            )
        content, is_error = render_tool_result(
            call.name, call.arguments, output, self.max_result_chars
        )
        return ToolResult(tool_call_id=call.id, content=content, is_error=is_error)


def build_registry(http: httpx.Client, max_result_chars: int = 16_000) -> ToolRegistry:
    registry = ToolRegistry(max_result_chars)
    registry.register(
        Tool(
            name="get_order",
            description=(
                "Get one Kestrel order by ID: customer ID, channel (trade or store), "
                "status (placed, shipped, delivered, cancelled or returned), total and "
                "promised date. Use it to check whether an order is still open."
            ),
            args_model=OrderIdArgs,
            function=partial(get_order, http),
        )
    )
    registry.register(
        Tool(
            name="get_shipment",
            description=(
                "Get the shipment for one Kestrel order: carrier, warehouse, shipped and "
                "delivered times, status and whether it is late. Orders that have not "
                "shipped yet have no shipment."
            ),
            args_model=OrderIdArgs,
            function=partial(get_shipment, http),
        )
    )
    registry.register(
        Tool(
            name="list_shipments",
            description=(
                "List Kestrel shipments, optionally for one carrier. late=true (the default) "
                "returns only shipments flagged late, meaning delivered after the promised "
                "time or lost. Returns at most `limit` rows (up to 20), not a full count."
            ),
            args_model=ShipmentListArgs,
            function=partial(list_shipments, http),
        )
    )
    registry.register(  # new in Chapter 10
        Tool(
            name="get_ticket",
            description=(
                "Get one Kestrel support ticket by ID: customer ID, the order it is about, "
                "channel, priority, status, subject and every message in the thread."
            ),
            args_model=TicketIdArgs,
            function=partial(get_ticket, http),
        )
    )
    registry.register(  # new in Chapter 10
        Tool(
            name="get_policy",
            description=(
                "Get the full text of one Kestrel policy (returns-policy or shipping-policy). "
                "Use it before telling a customer what Kestrel can offer."
            ),
            args_model=PolicyArgs,
            function=partial(get_policy, http),
        )
    )
    return registry
