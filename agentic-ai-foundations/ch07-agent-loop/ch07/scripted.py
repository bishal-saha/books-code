"""Scripted fake-model runs for `ops_agent --fake`, so the loop runs without a key.

The model's side (text, tool calls, ids and token counts) is written by hand and labelled
fake. The tool results are real: the registry calls the seeded Kestrel API.
"""

from ch07.fake_model import FakeModelClient
from ch07.model_client import ModelResponse, ToolCall, Usage

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
    orders = [{"order_id": o} for o in CHASED]
    final = (
        "O-0014614: the order record says delivered, but its Northline Freight shipment "
        "is lost (flagged late, promised 2025-04-18).\n"
        "O-0004943: shipped; Swiftway Parcel, in transit, not flagged late "
        "(promised 2025-12-22).\n"
        "O-0004365: placed on 2025-06-04 and not shipped yet (promised 2025-06-07).\n"
        "NEEDS INFO: O-9999999 does not exist in the order system; please check the ID.\n"
        "Northline Freight has other late shipments: all 10 that the list returned were "
        "delivered late.\n"
        "Carrier trace needed: O-0014614 (Northline Freight)."
    )
    return FakeModelClient(
        [
            _step(_calls("get_order", 1, orders), 1210, 96, "I'll look up all four orders."),
            _step(_calls("get_shipment", 5, orders[:2]), 1830, 70),
            _step(
                _calls("list_shipments", 7, [{"carrier": "Northline Freight", "late": True}]),
                2690,
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
    same = [{"order_id": "O-9999999"}]
    return FakeModelClient([_step(_calls("get_order", n, same), 900, 40) for n in range(1, 50)])


SCENARIOS = {"chased": chased, "stuck": stuck}
