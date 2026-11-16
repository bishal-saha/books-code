"""Maya's four-question support session, scripted for the fake model.

The model's side (text, tool calls, ids and token counts) is written by hand and labelled fake.
The tool results are real: the seeded Kestrel mock API answers every call.
"""

from ch10.budget import CallLimits, RunBudget
from ch10.fake_model import FakeModelClient, ScriptItem
from ch10.model_client import ModelResponse, ToolCall, Usage

TASK = "Help me with ticket T-000407."
FOLLOW_UPS = [
    "Has order O-0006066 shipped?",
    "What can we offer the customer?",
    "Is Swiftway Parcel late on other shipments?",
]

FAKE_BUDGET = RunBudget(max_steps=8, max_total_tokens=60_000, max_wall_seconds=90.0)
FAKE_LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30.0)


def _calls(*calls: tuple[str, str, dict]) -> ModelResponse:
    tool_calls = [ToolCall(id=i, name=name, arguments=args) for i, name, args in calls]
    usage = Usage(input_tokens=900, output_tokens=40)  # invented numbers
    return ModelResponse(text="", stop_reason="tool_call", usage=usage, tool_calls=tool_calls)


def _reply(text: str) -> ModelResponse:
    usage = Usage(input_tokens=1200, output_tokens=len(text.split()))  # invented numbers
    return ModelResponse(text=text, stop_reason="finished", usage=usage)


TURNS: list[list[ScriptItem]] = [
    [  # Help me with ticket T-000407.
        _calls(("toolu_fake_01", "get_ticket", {"ticket_id": "T-000407"})),
        _reply(
            "T-000407 is from customer C-001143 by email: 'Where is my order?' about order "
            "O-0006066. A colleague replied that we're looking into it. (get_ticket)"
        ),
    ],
    [  # Has order O-0006066 shipped?
        _calls(  # two parallel calls: one assistant message, one results message
            ("toolu_fake_02", "get_order", {"order_id": "O-0006066"}),
            ("toolu_fake_03", "get_shipment", {"order_id": "O-0006066"}),
        ),
        _reply(
            "Yes. O-0006066 (USD 829.98) shipped on 2025-12-03 from Main (Riverside) with "
            "Swiftway Parcel. It was promised by 2025-12-05 and is still in transit; the "
            "shipment is not flagged late because it has not been delivered. (get_shipment)"
        ),
    ],
    [  # What can we offer the customer?
        _calls(
            ("toolu_fake_04", "get_policy", {"name": "shipping-policy"}),
            ("toolu_fake_05", "get_policy", {"name": "returns-policy"}),
        ),
        _reply(
            "A shipment only counts as late once it is delivered after its promised date, and "
            "lost parcels count as late (shipping-policy). Support can approve refunds up to "
            "USD 500; O-0006066 is USD 829.98, so a refund needs Finance (returns-policy).\n"
            "NEEDS INFO: whether the customer wants to wait, or wants a refund."
        ),
    ],
    [  # Is Swiftway Parcel late on other shipments?
        _calls(
            (
                "toolu_fake_06",
                "list_shipments",
                {"carrier": "Swiftway Parcel", "late": True, "limit": 10},
            )
        ),
        _reply(
            "Yes. All 10 Swiftway Parcel shipments the list returned were delivered late, the "
            "most recent S-0000258 (promised 2025-11-19, delivered 2025-11-21). The list is "
            "capped at 10 rows, so it is not a full count. (list_shipments)"
        ),
    ],
]

FAKE_SUMMARY = _reply(  # fake-model output: the compaction call's scripted reply
    "IDs: ticket T-000407, customer C-001143, order O-0006066, shipment S-0005532.\n"
    "Findings: O-0006066 shipped 2025-12-03 from Main (Riverside) with Swiftway Parcel, "
    "promised by 2025-12-05, still in transit, not flagged late (origin: get_shipment). "
    "Order total USD 829.98 (origin: get_order). Late means delivered after the promised "
    "date; lost parcels count as late (origin: get_policy shipping-policy). Support approves "
    "refunds up to USD 500, Finance above that (origin: get_policy returns-policy).\n"
    "Decisions: none yet.\n"
    "Open questions: does the customer want to wait, or a refund?"
)


def maya_client(summary_at: tuple[int, int] | None = None) -> FakeModelClient:
    """The whole session's script. With compaction on, the summary reply goes in at
    (turn, step): the model call just before which the history first crosses the threshold."""
    script: list[ScriptItem] = []
    for t, turn in enumerate(TURNS):
        for n, item in enumerate(turn):
            if summary_at == (t, n):
                script.append(FAKE_SUMMARY)
            script.append(item)
    return FakeModelClient(script)
