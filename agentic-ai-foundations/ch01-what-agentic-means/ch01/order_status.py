"""Deterministic order-status workflow for a support ticket. No model call."""

import sys
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

import httpx
from pydantic import BaseModel

BASE_URL = "http://127.0.0.1:8700"  # the single Kestrel mock server
USAGE = "usage: python -m ch01.order_status TICKET_ID YYYY-MM-DD"


class WorkflowError(Exception):
    """A known state the workflow refuses to guess about."""


class TicketNotFound(WorkflowError):
    """The API has no ticket with this ID."""


class NoOrderOnTicket(WorkflowError):
    """The ticket is not about an order (a general enquiry)."""


class OrderNotFound(WorkflowError):
    """The API has no order with this ID."""


class NotShipped(WorkflowError):
    """The order exists but has no shipment yet (placed, or cancelled)."""


class UpstreamUnavailable(WorkflowError):
    """The API could not be reached, timed out or answered with an error."""


class Ticket(BaseModel):
    ticket_id: str
    order_id: str | None


class Order(BaseModel):
    order_id: str
    channel: Literal["store", "trade"]  # exercise 3 uses it


class Shipment(BaseModel):
    carrier: str
    status: Literal["in_transit", "delivered", "lost"]
    promised_by: datetime


class Verdict(StrEnum):
    DELIVERED = "delivered"
    LOST = "lost"
    LATE = "late"
    ON_TIME = "on_time"


class OrderStatus(BaseModel):
    ticket_id: str
    order_id: str
    carrier: str
    shipment_status: str
    promised_by: date
    verdict: Verdict
    next_step: str


def get_order_status(client: httpx.Client, ticket_id: str, today: date) -> OrderStatus:
    ticket = Ticket.model_validate(_get(client, f"/tickets/{ticket_id}", TicketNotFound))
    if ticket.order_id is None:
        raise NoOrderOnTicket(ticket_id)
    order = Order.model_validate(_get(client, f"/orders/{ticket.order_id}", OrderNotFound))
    shipment = Shipment.model_validate(
        _get(client, f"/orders/{order.order_id}/shipment", NotShipped)
    )
    promised = shipment.promised_by.date()

    if shipment.status == "delivered":
        verdict, next_step = Verdict.DELIVERED, "Confirm the delivery date with the customer."
    elif shipment.status == "lost":
        verdict, next_step = Verdict.LOST, "Open a carrier trace; a person decides on a reship."
    elif today > promised:
        verdict, next_step = Verdict.LATE, "Apologise, share tracking and open a carrier trace."
    else:
        verdict, next_step = Verdict.ON_TIME, "Share tracking and the promised date."

    return OrderStatus(
        ticket_id=ticket_id,
        order_id=order.order_id,
        carrier=shipment.carrier,
        shipment_status=shipment.status,
        promised_by=promised,
        verdict=verdict,
        next_step=next_step,
    )


def _get(client: httpx.Client, path: str, not_found: type[WorkflowError]) -> dict:
    """Return the JSON body; raise not_found on 404, UpstreamUnavailable on other failures."""
    try:
        response = client.get(path)
    except httpx.TransportError as exc:  # timeouts, refused connections, ...
        raise UpstreamUnavailable(f"Kestrel API unreachable for {path}") from exc
    if response.status_code == 404:
        raise not_found(response.json().get("error", path))
    if response.is_error:
        raise UpstreamUnavailable(f"{path} returned HTTP {response.status_code}")
    return response.json()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        today = date.fromisoformat(argv[2])
    except ValueError:
        print(USAGE, file=sys.stderr)
        return 2
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        try:
            status = get_order_status(client, argv[1], today)
        except WorkflowError as exc:
            print(f"error: {exc!r}", file=sys.stderr)
            return 1
    print(status.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
