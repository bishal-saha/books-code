"""Scripted fake-model replies for `round_trip --fake`, so the cycle runs without a key.

The model's side (text, tool calls, ids) is written by hand and labelled fake. The tool results
are real: the registry calls the seeded Kestrel API, so every reader gets the same rows.
"""

from ch06.fake_model import FakeModelClient
from ch06.model_client import ModelResponse, ToolCall, Usage

NO_USAGE = Usage(input_tokens=0, output_tokens=0)  # a fake model spends no tokens


def _call(n: int, name: str, order_id: str) -> ToolCall:
    return ToolCall(id=f"toolu_fake_{n:02d}", name=name, arguments={"order_id": order_id})


def single() -> tuple[str, FakeModelClient]:
    question = "Lakeside Lodge 1755 says order O-0000141 hasn't arrived. Is it still open?"
    first = ModelResponse(
        text="I'll look up order O-0000141.",
        stop_reason="tool_call",
        usage=NO_USAGE,
        tool_calls=[_call(1, "get_order", "O-0000141")],
    )
    final = ModelResponse(
        text=(
            "O-0000141 is still open: it has shipped but is not delivered yet "
            "(promised 2025-10-11)."
        ),
        stop_reason="finished",
        usage=NO_USAGE,
    )
    return question, FakeModelClient([first, final])


ORDERS = ["O-0012682", "O-0007023", "O-0000141", "O-0017612"]


def parallel() -> tuple[str, FakeModelClient]:
    question = f"Which of these Lakeside Lodge 1755 orders are still open: {', '.join(ORDERS)}?"
    first = ModelResponse(
        text="",
        stop_reason="tool_call",
        usage=NO_USAGE,
        tool_calls=[_call(n, "get_order", order_id) for n, order_id in enumerate(ORDERS, 1)],
    )
    final = ModelResponse(
        text=(
            "O-0012682: delivered.\nO-0007023: returned.\nO-0000141: shipped, still open.\n"
            "O-0017612: placed, still open.\nTwo of the four orders are still open."
        ),
        stop_reason="finished",
        usage=NO_USAGE,
    )
    return question, FakeModelClient([first, final])


SCENARIOS = {"single": single, "parallel": parallel}
