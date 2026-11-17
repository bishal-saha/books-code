"""Chapter 8's v2 operations tools, read-only, plus one stock lookup for the comparison.

From Chapter 8: get_delivery_status, list_shipments, get_ticket and get_policy, unchanged.
Left out: create_return_authorisation, because the harness runs every task several times and
must never create records. New in Chapter 11: get_stock, written to the same conventions.
"""

from functools import partial
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from ch11.lookups import fetch_policy_text, order_for_ticket
from ch11.registry import Tool, ToolError, ToolRegistry
from ch11.shaping import paginate, truncate

# --- Input models: every Field description and constraint ends up in the schema the model reads

Carrier = Literal["Northline Freight", "Swiftway Parcel", "Harbour Express", "Tallpine Logistics"]


class GetDeliveryStatusArgs(BaseModel):
    order_or_ticket_id: str = Field(
        pattern=r"^(O-\d{7}|T-\d{6})$",
        description="The id the user gave: an order id (O-0013833) or a ticket id (T-000281).",
    )


class ListShipmentsArgs(BaseModel):
    carrier: Carrier | None = Field(default=None, description="Only this carrier.")
    late: bool | None = Field(default=None, description="true: late shipments only.")
    limit: int = Field(default=10, ge=1, le=50, description="Shipments per page, 1 to 50.")
    cursor: str | None = Field(
        default=None, pattern=r"^\d{1,4}$", description="next_cursor from the previous page."
    )


class GetTicketArgs(BaseModel):
    ticket_id: str = Field(pattern=r"^T-\d{6}$", description="Ticket id, e.g. T-000281.")
    include_messages: bool = Field(
        default=False, description="true only when you need the customer's own words."
    )


class GetStockArgs(BaseModel):  # new in Chapter 11
    sku: str = Field(pattern=r"^SKU-\d{5}$", description="Product SKU, e.g. SKU-00042.")


class GetPolicyArgs(BaseModel):
    name: str = Field(
        pattern=r"^[A-Za-z0-9-]{1,60}$", description="Policy name, e.g. returns-policy."
    )
    offset: int = Field(default=0, ge=0, description="The offset a truncation marker gave.")


# --- The tools

TICKET_FIELDS = ("ticket_id", "subject", "status", "priority", "channel", "order_id")
SHIPMENT_FIELDS = (
    "shipment_id",
    "order_id",
    "carrier",
    "status",
    "promised_by",
    "delivered_at",
    "late",
)
FETCH_CAP = 500  # the mock returns at most 500 rows per request
POLICY_MAX_CHARS = 2_000


def get_delivery_status(http: httpx.Client, args: GetDeliveryStatusArgs) -> dict[str, Any]:
    order_id, ticket_id = args.order_or_ticket_id, None
    if order_id.startswith("T-"):
        ticket_id, order_id = order_id, order_for_ticket(http, order_id)
    order = http.get(f"/orders/{order_id}")
    if order.status_code == 404:
        if ticket_id:
            raise ToolError(
                f"Ticket {ticket_id} points to order {order_id}, which the orders "
                "system doesn't have. Tell the user; retrying won't help."
            )
        raise ToolError(
            f"No order {order_id}. Order ids look like O-0013833. "
            "If the user gave a ticket id, pass that instead."
        )
    order.raise_for_status()
    o = order.json()
    result = {"order_id": order_id, "order_status": o["status"]}
    ship = http.get(f"/orders/{order_id}/shipment")
    if ship.status_code == 404:  # not shipped: the order's promised date is all there is
        return {**result, "promised_date": o["promised_date"], "shipment": None}
    ship.raise_for_status()
    s = ship.json()
    return {
        **result,
        "carrier": s["carrier"],
        "shipment_status": s["status"],
        "promised_by": s["promised_by"],
        "delivered_at": s["delivered_at"],
        "late": s["late"],
    }


def list_shipments(http: httpx.Client, args: ListShipmentsArgs) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if args.carrier is not None:
        filters["carrier"] = args.carrier
    if args.late is not None:
        filters["late"] = str(args.late).lower()
    r = http.get("/shipments", params={**filters, "limit": FETCH_CAP})
    r.raise_for_status()
    rows = [{k: s.get(k) for k in SHIPMENT_FIELDS} for s in r.json()]
    page = paginate(rows, args.cursor, args.limit, FETCH_CAP)
    return {**page, "applied_filters": filters}


def get_ticket(http: httpx.Client, args: GetTicketArgs) -> dict[str, Any]:
    r = http.get(f"/tickets/{args.ticket_id}")
    if r.status_code == 404:
        raise ToolError(
            f"No ticket {args.ticket_id}. Ticket ids look like T-000281; check the "
            "id the user gave. For an order id, use get_delivery_status."
        )
    r.raise_for_status()
    t = r.json()
    result = {k: t.get(k) for k in TICKET_FIELDS}
    if args.include_messages:
        result["messages"] = t.get("messages", [])
    return result


def get_policy(http: httpx.Client, args: GetPolicyArgs) -> dict[str, Any]:
    text = fetch_policy_text(http, args.name)
    if text is None:
        names = http.get("/policies").json()
        raise ToolError(f"No policy named {args.name}. Available: {', '.join(names)}.")
    return {
        "name": args.name,
        "text": truncate(text, POLICY_MAX_CHARS, args.offset, tool="get_policy"),
    }


def get_stock(http: httpx.Client, args: GetStockArgs) -> dict[str, Any]:  # new in Chapter 11
    r = http.get(f"/stock/{args.sku}")
    if r.status_code == 404:
        raise ToolError(f"No product {args.sku}. SKUs look like SKU-00042.")
    r.raise_for_status()
    return r.json()


# --- Descriptions: what it returns, when to use it, what to use instead, what the inputs mean

DELIVERY_STATUS_DESCRIPTION = (
    "Returns delivery status for one order: order_status, carrier, shipment_status (in_transit, "
    "delivered or lost), promised_by, delivered_at (null until delivered) and a late flag; an "
    "unshipped order has shipment null and its promised_date instead. Pass "
    "the id the user gave, either an order id (O-0013833) or a ticket id (T-000281); for a "
    "ticket, the tool finds the order itself. To read what a ticket says, use get_ticket. To "
    "find late shipments across many orders, use list_shipments."
)
LIST_SHIPMENTS_DESCRIPTION = (
    "Lists shipments that match a carrier and a late flag (late means delivered after the "
    "promised date, or lost). Returns one page of rows with next_cursor for the next page and "
    "total, the number of matching rows (up to 500). Use it for questions about many "
    "shipments; for one order or ticket, use get_delivery_status."
)
GET_TICKET_DESCRIPTION = (
    "Returns what a support ticket says: subject, status, priority, channel and the linked "
    "order_id. Set include_messages=true only when you need the customer's own words. To check "
    "whether the ticket's order is late, use get_delivery_status instead."
)
GET_POLICY_DESCRIPTION = (
    "Returns the text of one Kestrel policy, such as returns-policy or shipping-policy, at most "
    "2,000 characters per call. If the text ends with a truncation marker, call again with the "
    "offset it gives. Use it for rules, windows and limits, not for a specific order."
)


GET_STOCK_DESCRIPTION = (
    "Returns on-hand stock for one SKU in each Kestrel warehouse. For several SKUs, call it "
    "once per SKU; the calls are independent."
)


def build_registry(http: httpx.Client, max_result_chars: int = 16_000) -> ToolRegistry:
    """The read-only tool set. http is bound here, so each function takes only args."""
    registry = ToolRegistry(max_result_chars)
    for tool in [
        Tool(
            name="get_delivery_status",
            description=DELIVERY_STATUS_DESCRIPTION,
            args_model=GetDeliveryStatusArgs,
            function=partial(get_delivery_status, http),
            hints={"order_or_ticket_id": "Use O- and 7 digits or T- and 6 digits."},
        ),
        Tool(
            name="list_shipments",
            description=LIST_SHIPMENTS_DESCRIPTION,
            args_model=ListShipmentsArgs,
            function=partial(list_shipments, http),
        ),
        Tool(
            name="get_ticket",
            description=GET_TICKET_DESCRIPTION,
            args_model=GetTicketArgs,
            function=partial(get_ticket, http),
        ),
        Tool(
            name="get_policy",
            description=GET_POLICY_DESCRIPTION,
            args_model=GetPolicyArgs,
            function=partial(get_policy, http),
        ),
        Tool(
            name="get_stock",
            description=GET_STOCK_DESCRIPTION,
            args_model=GetStockArgs,
            function=partial(get_stock, http),
        ),
    ]:
        registry.register(tool)
    return registry
