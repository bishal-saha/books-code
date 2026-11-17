"""The edges the checklist asks about, run on our own loop with a fake model.

uv run python -m ch12.edges     # needs the mock API: uv run kestrel up

The model is a fake: its replies are scripted below, so the output is fake-model output.
The tool calls are real and go to the Kestrel mock API, through Chapter 11's read-only tools.
"""

import itertools
import os
from collections.abc import Callable

from ch12.annotated_agent import RunResult, print_steps, run_agent
from ch12.budget import CallLimits, RunBudget
from ch12.fake_model import FakeModelClient, ScriptItem
from ch12.lookups import kestrel_client
from ch12.model_client import ModelResponse, ToolCall, Usage
from ch12.prompts import load_prompt
from ch12.registry import ToolRegistry
from ch12.settings import DEFAULT_KESTREL_URL
from ch12.tools import build_registry

BUDGET = RunBudget(max_steps=4, max_total_tokens=20_000, max_wall_seconds=60.0)
LIMITS = CallLimits(max_output_tokens=1_024, timeout_seconds=30.0)


def ask(name: str, arguments: dict, n: int) -> ModelResponse:
    """One scripted model turn that asks for a single tool call."""
    call = ToolCall(id=f"call_{n}", name=name, arguments=arguments)
    usage = Usage(input_tokens=900, output_tokens=40)
    return ModelResponse(text="", stop_reason="tool_call", usage=usage, tool_calls=[call])


def ticking_clock(step: float = 0.2) -> Callable[[], float]:
    """A clock that moves 0.2 s per reading, so the printed times are the same every run."""
    counter = itertools.count()
    return lambda: next(counter) * step


BAD_CALLS: list[ScriptItem] = [
    ask("get_delivery_status", {"order_or_ticket_id": "T-000281"}, 1),
    ask("get_delivery_status", {"order_or_ticket_id": "T-000281", "verbose": True}, 2),
    ask("track_parcel", {"order_id": "O-0013833"}, 3),  # not in the registry
    (
        "Ticket T-000281 is about order O-0013833, delivered late by Harbour Express on "
        "2025-06-27. NEEDS INFO: no tool tracks the parcel itself."
    ),
]
NEVER_ENDS: list[ScriptItem] = [
    ask("get_delivery_status", {"order_or_ticket_id": "T-000281"}, n) for n in range(1, 10)
]


def run(script: list[ScriptItem], registry: ToolRegistry) -> RunResult:
    system = load_prompt("ops_agent", 2).body
    question = "Where is the parcel for ticket T-000281?"
    client = FakeModelClient(script)
    return run_agent(client, system, question, registry, BUDGET, LIMITS, clock=ticking_clock())


def main() -> None:
    url = os.environ.get("KESTREL_URL", DEFAULT_KESTREL_URL)
    with kestrel_client(url) as http:
        registry = build_registry(http)  # Chapter 11's read-only tools

        print("== an invented argument, then an unknown tool (fake model)")
        result = run(BAD_CALLS, registry)
        print_steps(result, BUDGET)
        for n in (2, 3):  # the results of the second and third tool calls
            error = result.messages[2 * n].tool_results[0]
            print(f"tool result {n}: is_error={error.is_error} {error.content}")

        print("\n== a model that never ends its turn (fake model)")
        result = run(NEVER_ENDS, registry)
        print_steps(result, BUDGET)
        print(f"answer: {result.final_text!r}  (partial result, labelled {result.cause})")


if __name__ == "__main__":
    main()
