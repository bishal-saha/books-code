"""The system prompt and the two ticket helpers that every script in this chapter shares."""

import json

import httpx

SYSTEM_PROMPT = (
    "You draft replies for a Kestrel Outfitters support representative to review. "
    "Be polite and specific. Never promise a refund. "
    "Keep the reply under 150 words."
)


def fetch_ticket(base_url: str, ticket_id: str) -> dict:
    response = httpx.get(f"{base_url}/tickets/{ticket_id}", timeout=5.0)
    response.raise_for_status()
    return response.json()


def build_user_text(ticket: dict) -> str:
    return (
        f"Ticket {ticket['ticket_id']}: {ticket['subject']}\n\n"
        f"Messages so far:\n{json.dumps(ticket['messages'], indent=2)}\n\n"
        "Draft the next reply to the customer."
    )
