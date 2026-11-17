"""create_return_authorisation: an idempotent write tool with a program-derived key."""

import hashlib
import json
import re
from datetime import date, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ch12.lookups import fetch_policy_text, order_for_ticket
from ch12.registry import ToolError
from ch12.return_store import ReturnStore


class ReturnLine(BaseModel):
    sku: str = Field(pattern=r"^SKU-\d{5}$", description="Product SKU, e.g. SKU-00042.")
    quantity: int = Field(ge=1, le=100)


class CreateReturnArgs(BaseModel):
    ticket_id: str = Field(pattern=r"^T-\d{6}$", description="The ticket asking for the return.")
    lines: list[ReturnLine] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=3, max_length=500, description="The customer's reason.")


def derive_key(args: CreateReturnArgs) -> str:
    totals: dict[str, int] = {}
    for line in args.lines:  # one line of 2 and two lines of 1 are the same return
        totals[line.sku] = totals.get(line.sku, 0) + line.quantity
    normalised = json.dumps({"ticket": args.ticket_id, "lines": sorted(totals.items())})
    return hashlib.sha256(normalised.encode()).hexdigest()


def create_return_authorisation(
    store: ReturnStore, http: httpx.Client, today: date, args: CreateReturnArgs
) -> dict[str, Any]:
    key = derive_key(args)
    if existing := store.find(key):  # a repeat gets what was created, even if the world moved on
        return {**existing, "already_existed": True}
    order_id = check_return(http, args.ticket_id, today)  # raises ToolError if not allowed
    created, row = store.insert_pending(key, order_id, args.model_dump_json())
    return {**row, "already_existed": not created}


# --- Business rules: checked only for a new key

CONSUMER_WINDOW = re.compile(r"consumers\b[^.;]*?within\s+(\d{1,3})\s+days", re.IGNORECASE)
NOT_DELIVERED = {
    "cancelled": "Order {id} was cancelled, so there is nothing to return.",
    "returned": "Order {id} is already marked returned. Tell the user a person will check.",
}


def return_window_days(policy_text: str, channel: str) -> int | None:
    """The store-channel window in days if the policy states exactly one, else None."""
    if channel != "store":  # trade windows can change by contract, which the tool can't see
        return None
    found = {int(n) for n in CONSUMER_WINDOW.findall(policy_text)}
    return found.pop() if len(found) == 1 else None


def check_return(http: httpx.Client, ticket_id: str, today: date) -> str:
    """The ticket's order id if a return may go ahead; otherwise a ToolError for the model."""
    order_id = order_for_ticket(http, ticket_id)
    order = http.get(f"/orders/{order_id}")
    order.raise_for_status()
    status, channel = order.json()["status"], order.json()["channel"]
    if status != "delivered":
        default = "Order {id} is " + status + ", not delivered yet. Returns open after delivery."
        raise ToolError(NOT_DELIVERED.get(status, default).format(id=order_id))
    ship = http.get(f"/orders/{order_id}/shipment")
    ship.raise_for_status()
    delivered_at = ship.json()["delivered_at"]
    days = return_window_days(fetch_policy_text(http, "returns-policy") or "", channel)
    if delivered_at is None or days is None:  # fail closed: never guess the window
        raise ToolError(
            f"The return window for order {order_id} can't be confirmed from the order and the "
            "returns policy. Don't retry; tell the user a person will review the return."
        )
    closes = date.fromisoformat(delivered_at[:10]) + timedelta(days=days)
    if today > closes:
        raise ToolError(f"Order {order_id}'s {days}-day return window closed on {closes}.")
    return order_id


CREATE_RETURN_DESCRIPTION = (
    "Creates a pending return authorisation for the order behind a support ticket, for a "
    "person to approve. Pass the ticket_id, the lines to return (SKU and quantity) and the "
    "customer's reason. The tool finds the order itself and checks that it was delivered and "
    "is inside the returns window. Calling it again for the same ticket and lines returns the "
    "existing authorisation with already_existed=true; it never creates a second one. Use it "
    "only when the user asks for a return to be set up."
)
