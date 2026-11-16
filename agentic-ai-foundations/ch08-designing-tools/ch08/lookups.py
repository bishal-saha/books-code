"""Kestrel look-ups shared by the v2 tools and the write tool."""

import httpx

from ch08.registry import ToolError

TOOL_HTTP_TIMEOUT_S = 5.0  # per request phase (connect, read, ...), as in Chapter 7


def kestrel_client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=TOOL_HTTP_TIMEOUT_S)


def order_for_ticket(http: httpx.Client, ticket_id: str) -> str:
    """The order id a ticket points to, or a ToolError the model can act on."""
    r = http.get(f"/tickets/{ticket_id}")
    if r.status_code == 404:
        raise ToolError(
            f"No ticket {ticket_id}. Ticket ids look like T-000281; check the id the user gave."
        )
    r.raise_for_status()
    order_id = r.json().get("order_id")
    if not order_id:
        raise ToolError(f"Ticket {ticket_id} is not linked to an order, so there is no delivery.")
    return order_id


def fetch_policy_text(http: httpx.Client, name: str) -> str | None:
    """A policy's text, or None if Kestrel has no policy by that name."""
    r = http.get(f"/policies/{name}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()["body"]
