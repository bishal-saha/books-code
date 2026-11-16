"""The "before" set: Chapter 7's three operations tools, plus two first-draft support tools.

get_order, get_shipment and list_shipments are copied from Chapter 7's tools.py unchanged.
get_ticket and get_policy are new here, written the way a first attempt usually is: they
work, but their descriptions don't say when to use them or what to use instead.
"""

from functools import partial
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ch08.registry import Tool, ToolError, ToolRegistry


class OrderIdArgs(BaseModel):  # get_order and get_shipment take one order ID
    order_id: str = Field(
        description="Kestrel order ID, for example O-0000042.", pattern=r"^O-\d{7}$"
    )


class ShipmentListArgs(BaseModel):
    carrier: str | None = Field(default=None, description="Carrier name, e.g. Swiftway Parcel.")
    late: bool = Field(default=True, description="True: only late shipments.")
    limit: int = Field(default=10, ge=1, le=20, description="How many shipments to return.")


class TicketIdArgs(BaseModel):
    ticket_id: str = Field(description="Ticket ID.")


class PolicyNameArgs(BaseModel):
    name: str = Field(description="Policy name.")


def get_order(http: httpx.Client, args: OrderIdArgs) -> dict[str, Any]:
    response = http.get(f"/orders/{args.order_id}")
    if response.status_code == 404:
        raise ToolError(f"No order {args.order_id} exists.")
    response.raise_for_status()
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


def get_ticket(http: httpx.Client, args: TicketIdArgs) -> dict[str, Any]:
    response = http.get(f"/tickets/{args.ticket_id}")
    response.raise_for_status()  # a 404 surfaces as "get_ticket failed (HTTPStatusError)."
    return response.json()


def get_policy(http: httpx.Client, args: PolicyNameArgs) -> dict[str, Any]:
    response = http.get(f"/policies/{args.name}")
    response.raise_for_status()
    return response.json()


def first_draft_tools(http: httpx.Client) -> list[Tool]:
    """New in Chapter 8, written as a first draft: they work, but say little."""
    return [
        Tool("get_ticket", "Get a support ticket.", TicketIdArgs, partial(get_ticket, http)),
        Tool("get_policy", "Get a policy document.", PolicyNameArgs, partial(get_policy, http)),
    ]


def build_registry_v1(http: httpx.Client) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in [
        Tool(
            name="get_order",
            description=(
                "Get one Kestrel order by ID: customer ID, channel (trade or store), "
                "status (placed, shipped, delivered, cancelled or returned), total and "
                "promised date. Use it to check whether an order is still open."
            ),
            args_model=OrderIdArgs,
            function=partial(get_order, http),
        ),
        Tool(
            name="get_shipment",
            description=(
                "Get the shipment for one Kestrel order: carrier, warehouse, shipped and "
                "delivered times, status and whether it is late. Orders that have not "
                "shipped yet have no shipment."
            ),
            args_model=OrderIdArgs,
            function=partial(get_shipment, http),
        ),
        Tool(
            name="list_shipments",
            description=(
                "List Kestrel shipments, optionally for one carrier. late=true (the default) "
                "returns only shipments flagged late, meaning delivered after the promised "
                "time or lost. Returns at most `limit` rows (up to 20), not a full count."
            ),
            args_model=ShipmentListArgs,
            function=partial(list_shipments, http),
        ),
        *first_draft_tools(http),
    ]:
        registry.register(tool)
    return registry
