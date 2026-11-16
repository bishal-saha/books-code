"""Maya's four-question session through the loop, with the fake model and the mock API.

    uv run python -m ch10.demo                     # compact (the default here)
    uv run python -m ch10.demo --strategy trim

Token figures are local CHARS_PER_TOKEN estimates of the real requests, Kestrel data included.
The thresholds are tiny on purpose, so a four-question session crosses them.
"""

import argparse
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx

from ch10.agent import RunResult, run_agent, tool_summary
from ch10.prompts import load_prompt
from ch10.scripted import FAKE_BUDGET, FAKE_LIMITS, FOLLOW_UPS, TASK, maya_client
from ch10.settings import DEFAULT_KESTREL_URL
from ch10.state import ContextPolicy, ConversationState
from ch10.tools import build_registry

DEMO_POLICIES = {
    "compact": ContextPolicy(
        strategy="compact",
        trim_target_tokens=3_000,
        compaction_threshold_tokens=1_500,
        compaction_keep_units=2,
        compaction_max_tokens=500,
    ),
    "trim": ContextPolicy(strategy="trim", trim_target_tokens=1_500),
}
SUMMARY_AT = (3, 1)  # turn 4, step 2: where this script's history first crosses 1,500 tokens


@contextmanager
def kestrel() -> Iterator[str]:
    """The server from `uv run kestrel up` if it answers, otherwise the same seeded data."""
    try:
        httpx.get(f"{DEFAULT_KESTREL_URL}/health", timeout=1.0).raise_for_status()
    except httpx.HTTPError:
        from kestrel.services import serve_in_thread

        server, url = serve_in_thread(scale=1.0)
        try:
            yield url
        finally:
            server.shutdown()
    else:
        yield DEFAULT_KESTREL_URL


def show_context(turn: int, result: RunResult, out: Callable[[str], None] = print) -> None:
    """One line per step: the history size as sent, its tools, any trim or compaction."""
    for s in result.steps:
        line = f"turn {turn} step {s.index + 1}  history {s.history_tokens:>5} tokens  "
        line += tool_summary(s.tool_calls) or "reply"
        if s.context is not None:
            c = s.context
            if c.kind == "trim":
                line += f"\n    trim: dropped {c.units_dropped} units"
            else:
                line += f"\n    compaction: {c.outcome}, {c.units_summarised} units summarised"
            line += f", {c.tokens_before} -> {c.tokens_after} tokens"
        out(line)
    out(f"turn {turn} stopped: {result.cause}")


def main(strategy: str) -> None:
    policy = DEMO_POLICIES[strategy]
    client = maya_client(SUMMARY_AT if strategy == "compact" else None)
    system = load_prompt("support_agent", 1).body
    print(f"[fake model: scripted replies; tool results from the mock API; {strategy}]")
    with kestrel() as url, httpx.Client(base_url=url, timeout=10.0) as http:
        registry = build_registry(http)
        state = ConversationState.start(TASK)
        for turn, question in enumerate([None, *FOLLOW_UPS], start=1):
            if question is not None:
                state.add_user(question)
            result = run_agent(client, system, state, registry, FAKE_BUDGET, FAKE_LIMITS, policy)
            show_context(turn, result)
            state = result.state  # continue from the returned state, never the old one
    print(f"compactions: {state.compactions}  summary kept: {state.summary is not None}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strategy", choices=sorted(DEMO_POLICIES), default="compact")
    main(parser.parse_args().strategy)
