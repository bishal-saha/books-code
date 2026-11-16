"""The selection check: does the model's first tool call name an acceptable tool, with
arguments that validate? Plus, for ticket-to-delivery requests, the tool calls to an answer.

uv run python -m ch08.selection_check --fake            # scripted fake model, no key
uv run --env-file .env python -m ch08.selection_check   # live: 5 runs per request and set
"""

import argparse
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory

import httpx
from pydantic import BaseModel, ValidationError

from ch08.agent import RunResult, run_agent
from ch08.budget import CallLimits, RunBudget
from ch08.lookups import kestrel_client
from ch08.model_client import Message, ModelClient, ToolCall
from ch08.prompts import load_prompt
from ch08.registry import ToolRegistry
from ch08.return_store import ReturnStore
from ch08.settings import DEFAULT_KESTREL_URL, Settings
from ch08.tools import build_registry
from ch08.tools_v1 import build_registry_v1

FIXTURE = Path(__file__).parent / "selection_fixture.jsonl"
TODAY = date(2025, 12, 16)  # the fixed date the book's examples use


class Entry(BaseModel):
    request: str
    expected: dict[str, list[str]]  # tool set name -> acceptable first tools
    ticket_to_delivery: bool = False


class SetReport(BaseModel):
    name: str
    acceptable: int = 0  # first calls that scored True
    attempts: int = 0
    tool_calls: list[int] = []  # per ticket-to-delivery run: tool calls until the answer


def load_fixture(path: Path = FIXTURE) -> list[Entry]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Entry.model_validate(json.loads(line)) for line in lines if line.strip()]


def score_first_call(
    call: ToolCall | None, acceptable: list[str], args_models: dict[str, type[BaseModel]]
) -> bool:
    """True if the first tool call names an acceptable tool with valid arguments."""
    if call is None or call.name not in acceptable:
        return False
    try:
        args_models[call.name].model_validate(call.arguments)
    except ValidationError:
        return False
    return True


def first_call(
    client: ModelClient, system: str, request: str, registry: ToolRegistry, max_tokens: int
) -> ToolCall | None:
    messages = [Message(role="user", content=request)]
    response = client.complete(system, messages, max_tokens, registry.definitions())
    return response.tool_calls[0] if response.tool_calls else None


def count_tool_calls(result: RunResult) -> int:
    """Tool calls in the step log, whether requested one per step or together."""
    return sum(len(step.tool_calls) for step in result.steps)


def check_set(
    client: ModelClient,
    system: str,
    name: str,
    registry: ToolRegistry,
    entries: list[Entry],
    runs: int,
    budget: RunBudget,
    limits: CallLimits,
) -> SetReport:
    report = SetReport(name=name)
    for entry in entries:
        acceptable = entry.expected.get(name)
        if acceptable is None:  # no list for this set: skip the entry
            continue
        for _ in range(runs):
            call = first_call(client, system, entry.request, registry, limits.max_output_tokens)
            report.attempts += 1
            report.acceptable += score_first_call(call, acceptable, registry.args_models())
            if entry.ticket_to_delivery:
                result = run_agent(client, system, entry.request, registry, budget, limits)
                report.tool_calls.append(count_tool_calls(result))
    return report


def format_report(reports: list[SetReport], runs: int) -> str:
    lines = [f"runs per request: {runs}", "set  acceptable first calls  tool calls to answer"]
    for r in reports:
        calls = f"{mean(r.tool_calls):.1f}" if r.tool_calls else "-"
        lines.append(f"{r.name:<4} {r.acceptable:>3}/{r.attempts:<21} {calls}")
    return "\n".join(lines)


def run_check(
    client: ModelClient, http: httpx.Client, store: ReturnStore, runs: int,
    budget: RunBudget, limits: CallLimits, out: Callable[[str], None] = print,
) -> list[SetReport]:  # fmt: skip
    system = load_prompt("ops_agent", 2).body  # the same prompt for both sets
    entries = load_fixture()
    sets = {"v1": build_registry_v1(http), "v2": build_registry(http, store, TODAY)}
    reports = [
        check_set(client, system, name, reg, entries, runs, budget, limits)
        for name, reg in sets.items()
    ]
    out(format_report(reports, runs))
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare first tool calls for v1 and v2.")
    parser.add_argument("--fake", action="store_true", help="scripted fake model, no key")
    parser.add_argument("--runs", type=int, default=5, help="runs per request and tool set")
    args = parser.parse_args()

    client: ModelClient
    if args.fake:
        from ch08.scripted import FAKE_BUDGET, FAKE_LIMITS, selector

        client, runs, budget, limits = selector(), 1, FAKE_BUDGET, FAKE_LIMITS
        kestrel_url = DEFAULT_KESTREL_URL
        print("[fake model: scripted tool choices; tool results from Kestrel]")
    else:
        from ch08.anthropic_adapter import AnthropicAdapter

        settings = Settings.from_env()
        if settings.api_key is None:
            raise SystemExit("error: set ANTHROPIC_API_KEY in .env (or use --fake)")
        client, runs = AnthropicAdapter(settings), args.runs
        budget = RunBudget(settings.run_max_steps, settings.run_max_tokens,
                           settings.run_max_seconds)  # fmt: skip
        limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
        kestrel_url = settings.kestrel_url
        print(f"model: {settings.model}  date: {date.today()}")
    with kestrel_client(kestrel_url) as http, TemporaryDirectory() as tmp:
        run_check(client, http, ReturnStore(f"{tmp}/returns.sqlite"), runs, budget, limits)


if __name__ == "__main__":
    main()
