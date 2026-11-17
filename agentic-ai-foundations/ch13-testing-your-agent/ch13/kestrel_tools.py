"""The operations agent's read-only tool set: Chapter 11's tools without the policy pair.

Every tool here only reads from the Kestrel mock API, because an eval runs each golden task
several times and must never create records. Chapter 8's return tool stays in its own folder.
"""

from functools import partial
from typing import Any

import httpx
from pydantic import Field

from ch13.tools import StrictArgs, Tool, ToolError, ToolRegistry, build_registry


class SkuArgs(StrictArgs):
    sku: str = Field(description="Kestrel SKU, for example SKU-00042.", pattern=r"^SKU-\d{5}$")


class TicketIdArgs(StrictArgs):
    ticket_id: str = Field(description="Ticket ID, for example T-000042.", pattern=r"^T-\d{6}$")


def get_stock(http: httpx.Client, args: SkuArgs) -> dict[str, Any]:
    response = http.get(f"/stock/{args.sku}")
    if response.status_code == 404:
        raise ToolError(f"No product {args.sku}.")
    response.raise_for_status()
    return response.json()


def get_ticket(http: httpx.Client, args: TicketIdArgs) -> dict[str, Any]:
    response = http.get(f"/tickets/{args.ticket_id}")
    if response.status_code == 404:
        raise ToolError(f"No ticket {args.ticket_id}.")
    response.raise_for_status()
    ticket = response.json()
    ticket.pop("messages", None)  # the operations agent needs the record, not the conversation
    return ticket


def build_ops_registry(http: httpx.Client, max_result_chars: int = 16_000) -> ToolRegistry:
    registry = build_registry(http, max_result_chars)  # get_order, get_shipment, list_shipments
    for tool in [
        Tool(
            name="get_stock",
            description=(
                "Get on-hand stock for one SKU in each Kestrel warehouse. For several SKUs, "
                "call it once per SKU."
            ),
            args_model=SkuArgs,
            function=partial(get_stock, http),
        ),
        Tool(
            name="get_ticket",
            description=(
                "Get one support ticket's record: customer, linked order ID, channel, "
                "priority, status and subject (not the message thread)."
            ),
            args_model=TicketIdArgs,
            function=partial(get_ticket, http),
        ),
    ]:
        registry.register(tool)
    return registry
