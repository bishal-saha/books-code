"""A scripted fake model for `selection_check --fake`, so the check runs without a key.

Its tool choices and token counts are written by hand and labelled fake; they show the
report's format, not how any real model behaves. The tool results are real Kestrel data.
"""

from collections.abc import Sequence

from ch08.budget import CallLimits, RunBudget
from ch08.model_client import (
    Message,
    ModelResponse,
    ToolCall,
    ToolChoice,
    ToolDefinition,
    Usage,
)

FAKE_BUDGET = RunBudget(max_steps=8, max_total_tokens=60_000, max_wall_seconds=90.0)
FAKE_LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30.0)

Step = list[tuple[str, dict]]  # the tool calls the fake requests in one response

# (request, tool set) -> the steps the fake takes before it answers
PLANS: dict[tuple[str, str], list[Step]] = {
    ("Is order O-0013833 late?", "v1"): [[("get_order", {"order_id": "O-0013833"})]],
    ("Is order O-0013833 late?", "v2"): [
        [("get_delivery_status", {"order_or_ticket_id": "O-0013833"})]
    ],
    ("Ticket T-000281 asks where the order is. Was it late?", "v1"): [
        [("get_ticket", {"ticket_id": "T-000281"})],
        [("get_shipment", {"order_id": "O-0013833"})],
    ],
    ("Ticket T-000281 asks where the order is. Was it late?", "v2"): [
        [("get_delivery_status", {"order_or_ticket_id": "T-000281"})]
    ],
    ("What does ticket T-000281 say? Quote the customer.", "v1"): [
        [("get_ticket", {"ticket_id": "T-000281"})]
    ],
    ("What does ticket T-000281 say? Quote the customer.", "v2"): [
        [("get_ticket", {"ticket_id": "T-000281", "include_messages": True})]
    ],
    # v1's carrier is a free string, so "Swiftway" validates: a wrong value the metric can't see
    ("Which Swiftway Parcel shipments are late?", "v1"): [
        [("list_shipments", {"carrier": "Swiftway"})]
    ],
    ("Which Swiftway Parcel shipments are late?", "v2"): [
        [("list_shipments", {"carrier": "Swiftway Parcel", "late": True})]
    ],
    ("How many days do consumers have to return an item?", "v1"): [
        [("get_policy", {"name": "returns-policy"})]
    ],
    ("How many days do consumers have to return an item?", "v2"): [
        [("get_policy", {"name": "returns-policy"})]
    ],
    ("Ticket T-000410 wants to return 1 x SKU-00042, it doesn't fit. Set up the return.", "v2"): [
        [
            (
                "create_return_authorisation",
                {
                    "ticket_id": "T-000410",
                    "lines": [{"sku": "SKU-00042", "quantity": 1}],
                    "reason": "Doesn't fit.",
                },
            )
        ]
    ],
}


class ScriptedSelector:
    """Picks its tool calls from PLANS by the request and by which tool set it was offered."""

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        tools: Sequence[ToolDefinition] = (),
        tool_choice: ToolChoice | None = None,
        timeout: float | None = None,
    ) -> ModelResponse:
        tool_set = "v2" if any(t.name == "get_delivery_status" for t in tools) else "v1"
        plan = PLANS[(messages[0].content, tool_set)]
        step = sum(1 for m in messages if m.role == "assistant")
        usage = Usage(input_tokens=900 + 400 * step, output_tokens=60)  # invented numbers
        if step >= len(plan):
            return ModelResponse(text="[scripted answer]", stop_reason="finished", usage=usage)
        calls = [
            ToolCall(id=f"toolu_fake_{step}_{n}", name=name, arguments=args)
            for n, (name, args) in enumerate(plan[step])
        ]
        return ModelResponse(text="", stop_reason="tool_call", usage=usage, tool_calls=calls)


def selector() -> ScriptedSelector:
    return ScriptedSelector()
