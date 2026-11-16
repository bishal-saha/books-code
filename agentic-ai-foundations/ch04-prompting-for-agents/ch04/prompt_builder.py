"""Load versioned prompt files, render a ticket as delimited data, and send one request."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ch04.model_client import Message, ModelClient

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Prompt(BaseModel):
    name: str
    version: int
    change: str
    body: str


class TicketMessage(BaseModel):
    author: str  # "customer" or a staff ID such as E-0250
    sent_at: datetime
    body: str


class Ticket(BaseModel):
    """The fields of GET /tickets/{ticket_id} that the builder uses."""

    model_config = ConfigDict(extra="ignore")  # priority, status, customer_id: not used
    ticket_id: str
    order_id: str | None  # some tickets name no order
    channel: str  # email, chat, phone or web form
    subject: str
    messages: list[TicketMessage]


class TicketData(BaseModel):
    """Raw JSON text the API returned for one ticket, rendered inside <data>."""

    order: str | None = None  # GET /orders/{order_id}
    shipment: str | None = None  # GET /orders/{order_id}/shipment
    policies: str = "none"  # GET /policies/{name}, current policies only


class Draft(BaseModel):
    ticket_id: str
    prompt_version: int
    text: str
    stop_reason: str
    input_tokens: int
    output_tokens: int


def load_prompt(name: str, version: int) -> Prompt:
    text = (PROMPTS_DIR / f"{name}_v{version}.md").read_text(encoding="utf-8")
    _, header, body = text.split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    prompt = Prompt(**fields, body=body.strip())
    if prompt.version != version:
        raise ValueError(f"{name}_v{version}.md declares version {prompt.version}")
    return prompt


def _esc(text: str) -> str:
    # Replace < and > so customer text can't open or close a tag.
    return text.replace("<", "&lt;").replace(">", "&gt;")


def render_ticket(ticket: Ticket, data: TicketData) -> str:
    messages = [
        f'<message from="{"customer" if m.author == "customer" else "staff"}" '
        f'sent_at="{m.sent_at.date().isoformat()}">{_esc(m.body)}</message>'
        for m in ticket.messages
    ]
    lines = [
        "<ticket>",
        f"<ticket_id>{_esc(ticket.ticket_id)}</ticket_id>",
        f"<channel>{_esc(ticket.channel)}</channel>",
        f"<order_id>{_esc(ticket.order_id or 'none')}</order_id>",
        f"<subject>{_esc(ticket.subject)}</subject>",
        "<messages>",
        *messages,
        "</messages>",
        "</ticket>",
        "<data>",
        f"<order>{_esc(data.order or 'none')}</order>",
        f"<shipment>{_esc(data.shipment or 'none')}</shipment>",
        f"<policies>{_esc(data.policies)}</policies>",
        "</data>",
    ]
    return "\n".join(lines)


def build_messages(ticket: Ticket, data: TicketData) -> list[Message]:
    return [Message(role="user", content=render_ticket(ticket, data))]


def draft_reply(
    client: ModelClient, prompt: Prompt, ticket: Ticket, data: TicketData, max_tokens: int
) -> Draft:
    response = client.complete(
        system=prompt.body,  # identical for every ticket
        messages=build_messages(ticket, data),
        max_tokens=max_tokens,
    )
    return Draft(
        ticket_id=ticket.ticket_id,
        prompt_version=prompt.version,
        text=response.text,
        stop_reason=response.stop_reason,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
