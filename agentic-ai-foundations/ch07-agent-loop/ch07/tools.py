"""Chapter 6's tools, registry and dispatcher, plus a shipment list and a timeout branch.

New in Chapter 7: `list_shipments` (GET /shipments), and dispatch() reports a tool timeout as
a failure worth one retry, unlike a missing order, which no retry will fix.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from ch07.model_client import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)
MAX_RESULT_CHARS = 8_000  # backstop; tools should keep their own output small first


# --- The arguments the tools accept: a pydantic model, as in Chapter 5 ---


class OrderIdArgs(BaseModel):  # get_order and get_shipment take one order ID
    order_id: str = Field(
        description="Kestrel order ID, for example O-0000042.", pattern=r"^O-\d{7}$"
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


# --- The registry: one record per tool, definitions and dispatch derived from it ---


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    function: Callable[[Any], Any]  # takes the validated args only; bind the rest with partial


def as_data(text: str) -> str:
    """Chapter 4's rule for untrusted data: escape the tag characters, cap, delimit."""
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + " [truncated]"
    return f"<data>{text}</data>"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

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
        return ToolResult(tool_call_id=call.id, content=as_data(json.dumps(output, default=str)))


def build_registry(http: httpx.Client) -> ToolRegistry:
    registry = ToolRegistry()
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
    return registry
