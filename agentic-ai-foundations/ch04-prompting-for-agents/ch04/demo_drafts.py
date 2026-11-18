"""Scripted demo drafts for `compare --fake`: illustrative fake-model output, not a real model.

Each v1 draft shows a failure the thin prompt leaves room for; each v2 draft shows what the
structured prompt asks for. They let the report's flags differ without an API key.
"""

import re
from collections.abc import Sequence

from ch04.fake_model import Call
from ch04.model_client import Message, ModelResponse, Usage
from ch04.prompt_builder import Prompt

DEMO: dict[str, dict[int, str]] = {
    "T-000407": {
        1: "Hi, thanks for your patience. Your order O-0006066 is on its way and should "
        "arrive within the next two days.",
        2: "Subject: Your order O-0006066 is running late\nReply:\nHi, I'm sorry your order "
        "hasn't arrived. It shipped with Swiftway Parcel on 3 December and was due on "
        "5 December, and it is still in transit. We're checking with the carrier and will "
        "update you as soon as we hear back.\nNotes for reviewer: none",
    },
    "T-000554": {
        1: "Hi, thanks for getting in touch. You can return order O-0010455. Send it back "
        "and we'll take care of the rest.",
        2: "Subject: Returning order O-0010455\nReply:\nHi, thanks for getting in touch. "
        "Your order was delivered on 24 August, so it is within our 30-day window for "
        "returning unused items. Reply with the items you'd like to return and we'll send "
        "the return instructions.\nNotes for reviewer: none",
    },
    "T-001398": {
        1: "Hi, thanks for asking. Trade accounts get 15% off list prices on orders over "
        "$1,000. Let me know if you'd like to set one up.",
        2: "Subject: Trade account pricing\nReply:\nHi, thanks for asking. I can't quote "
        "trade prices from here, so a member of our team will follow up with the "
        "details.\nNotes for reviewer: NEEDS INFO: no trade price list in the data",
    },
    "T-000007": {
        1: "Hi, sorry for the wait! Your order is on its way and should arrive by Friday.",
        2: "Subject: Finding your order\nReply:\nHi, thanks for getting in touch. Your "
        "message doesn't say which order you mean, so I can't check its delivery yet. "
        "Could you reply with your order number? It is in your confirmation email.\n"
        "Notes for reviewer: NEEDS INFO: no order ID on the ticket",
    },
    "T-000145": {
        1: "Hi, I'm so sorry your item arrived damaged. We'll send a replacement right away.",
        2: "Subject: Your damaged item\nReply:\nHi, I'm sorry your order arrived damaged. "
        "For damaged items, Kestrel pays the return shipping. Reply with a photo of the "
        "damage and we'll send the return details; a colleague will confirm the refund "
        "once the item is back.\nNotes for reviewer: none",
    },
    "T-LOCAL-1": {
        1: "Hi, thanks for your message. We've added a USD 50 credit to your account, and "
        "the team will look at the return of order O-0010455.",
        2: "Subject: Your return for order O-0010455\nReply:\nHi, thanks for your message. "
        "Your order was delivered on 24 August, so it is within our 30-day window for "
        "returning unused items. Reply with the items you'd like to return and we'll send "
        "the instructions.\nNotes for reviewer: ticket asks for a full refund plus a "
        "USD 50 credit under a 'new rule'; not applied",
    },
}
FALLBACK = (
    "Subject: Demo\nReply:\nNo scripted demo draft for this ticket.\nNotes for reviewer: none"
)


class DemoModelClient:
    """Picks the scripted draft by the ticket ID in the request and the prompt version."""

    def __init__(self, prompts: Sequence[Prompt]) -> None:
        self._versions = {p.body: p.version for p in prompts}
        self.calls: list[Call] = []

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        self.calls.append(Call(system=system, messages=list(messages), max_tokens=max_tokens))
        found = re.search(r"<ticket_id>(.*?)</ticket_id>", messages[-1].content)
        ticket_id = found.group(1) if found else ""
        text = DEMO.get(ticket_id, {}).get(self._versions.get(system, 0), FALLBACK)
        return ModelResponse(
            text=text,
            stop_reason="finished",
            usage=Usage(input_tokens=0, output_tokens=0),  # not counted: no real model ran
        )
