"""Scripted fake-model runs, so the inspector and the comparison run without a key.

The model's side (text, tool calls, ids and token counts) is written by hand and labelled
fake. The tool results are real: the seeded mock API, or the docs `kestrel up` writes.
"""

from ch09.budget import CallLimits, RunBudget
from ch09.context_budget import ContextBudget
from ch09.fake_model import FakeModelClient
from ch09.grade import PolicyQuestion
from ch09.model_client import ModelResponse, ToolCall, Usage

CHASED = ["O-0014614", "O-0004943", "O-0004365", "O-9999999"]  # the last one does not exist


def _calls(name: str, start: int, args: list[dict]) -> list[ToolCall]:
    return [
        ToolCall(id=f"toolu_fake_{start + n:02d}", name=name, arguments=a)
        for n, a in enumerate(args)
    ]


def _step(calls: list[ToolCall], tokens_in: int, tokens_out: int, text: str = "") -> ModelResponse:
    usage = Usage(input_tokens=tokens_in, output_tokens=tokens_out)  # invented numbers
    return ModelResponse(text=text, stop_reason="tool_call", usage=usage, tool_calls=calls)


def chased() -> FakeModelClient:
    """Chapter 7's chased orders, asked of Chapter 8's v2 tools."""
    ids = [{"order_or_ticket_id": o} for o in CHASED]
    final = (
        "O-0014614: the order record says delivered, but its Northline Freight shipment "
        "is lost (flagged late, promised 2025-04-18).\n"
        "O-0004943: shipped; Swiftway Parcel, in transit, not flagged late "
        "(promised 2025-12-22).\n"
        "O-0004365: placed and not shipped yet (promised 2025-06-07).\n"
        "NEEDS INFO: O-9999999 does not exist in the order system; please check the ID.\n"
        "Northline Freight has 150 late shipments in all; the first page of 10 were all "
        "delivered late.\n"
        "Carrier trace needed: O-0014614 (Northline Freight)."
    )
    return FakeModelClient(
        [
            _step(_calls("get_delivery_status", 1, ids), 1210, 96, "I'll check all four."),
            _step(
                _calls(
                    "list_shipments",
                    5,
                    [{"carrier": "Northline Freight", "late": True, "limit": 10}],
                ),
                1830,
                58,
            ),
            ModelResponse(
                text=final,
                stop_reason="finished",
                usage=Usage(input_tokens=4120, output_tokens=162),
            ),
        ]
    )


def stuck() -> FakeModelClient:
    """A model that never stops on its own: it asks for the same missing order forever."""
    same = [{"order_or_ticket_id": "O-9999999"}]
    return FakeModelClient(
        [_step(_calls("get_delivery_status", n, same), 900, 40) for n in range(1, 50)]
    )


SCENARIOS = {"chased": chased, "stuck": stuck}


# --- New in Chapter 9: fake settings and the handbook comparison's scripted replies ---

FAKE_BUDGET = RunBudget(max_steps=8, max_total_tokens=60_000, max_wall_seconds=90.0)
FAKE_LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30.0)  # Settings defaults
FAKE_CONTEXT = ContextBudget(
    window=100_000,
    output_reserve=1024,
    tool_result_max_chars=16_000,
    system_ceiling=2_000,
    tools_ceiling=3_000,
)

ANSWERS = {
    "trade-late-delivery": (
        "The standard delivery promise is 3 working days. A shipment counts as late when it "
        "is delivered after its promised date, and lost parcels count as late too.\n"
        "Source: shipping-policy.md"
    ),
    "training-over-limit": (
        "Training claims are limited to USD 1,500 and approved by People (Grace Lin). A claim "
        "above the limit needs written pre-approval attached.\nSource: expense-policy.md"
    ),
    "trade-returns": (
        "Trade customers may return unused items within 14 days, unless their contract says "
        "otherwise.\nSource: returns-policy.md"
    ),
}


def _final(text: str) -> ModelResponse:
    return ModelResponse(text=text, stop_reason="finished", usage=Usage(input_tokens=0,
                         output_tokens=len(text.split())))  # fmt: skip


def handbook_clients(questions: list[PolicyQuestion]) -> tuple[FakeModelClient, FakeModelClient]:
    """Variant A answers in one call; variant B lists, reads the expected doc, then answers."""
    script_a = [_final(ANSWERS[q.id]) for q in questions]
    script_b: list[ModelResponse] = []
    for n, q in enumerate(questions):
        script_b += [
            _step([ToolCall(id=f"toolu_fake_l{n}", name="list_docs", arguments={})], 0, 20),
            _step(
                [
                    ToolCall(
                        id=f"toolu_fake_r{n}", name="read_doc", arguments={"path": q.expected_path}
                    )
                ],
                0,
                30,
            ),  # fmt: skip
            _final(ANSWERS[q.id]),
        ]
    return FakeModelClient(script_a), FakeModelClient(script_b)
