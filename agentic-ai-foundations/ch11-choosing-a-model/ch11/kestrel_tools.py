"""The read-only tool set the comparison uses: Chapter 9's three tools plus four more reads.

Every tool here only reads from the Kestrel mock API, because the harness runs each task
several times per configuration and must never create records.
"""

from functools import partial
from typing import Any

import httpx
from pydantic import Field

from ch11.tools import StrictArgs, Tool, ToolError, ToolRegistry, build_registry


class SkuArgs(StrictArgs):
    sku: str = Field(description="Kestrel SKU, for example SKU-00042.", pattern=r"^SKU-\d{5}$")


class TicketIdArgs(StrictArgs):
    ticket_id: str = Field(description="Ticket ID, for example T-000042.", pattern=r"^T-\d{6}$")


class PolicyNameArgs(StrictArgs):
    name: str = Field(
        description="Policy name from list_policies, e.g. returns-policy.",
        pattern=r"^[A-Za-z0-9-]{1,60}$",
    )


class NoArgs(StrictArgs):
    pass


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
    ticket.pop("messages", None)  # the triage task needs the record, not the conversation
    return ticket


def list_policies(http: httpx.Client, args: NoArgs) -> list[str]:
    response = http.get("/policies")
    response.raise_for_status()
    return response.json()


def get_policy(http: httpx.Client, args: PolicyNameArgs) -> dict[str, Any]:
    response = http.get(f"/policies/{args.name}")
    if response.status_code == 404:
        names = ", ".join(http.get("/policies").json())
        raise ToolError(f"No policy named {args.name}. Available: {names}.")
    response.raise_for_status()
    return response.json()


def build_compare_registry(http: httpx.Client, max_result_chars: int = 16_000) -> ToolRegistry:
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
        Tool(
            name="list_policies",
            description="List the names of Kestrel's policy documents. Takes no arguments.",
            args_model=NoArgs,
            function=partial(list_policies, http),
        ),
        Tool(
            name="get_policy",
            description=(
                "Get the full text of one policy by its name from list_policies. Some "
                "documents are superseded versions; their text says so."
            ),
            args_model=PolicyNameArgs,
            function=partial(get_policy, http),
        ),
    ]:
        registry.register(tool)
    return registry
