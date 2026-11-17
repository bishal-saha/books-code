"""The research assistant's command line: one question, one run, one trace, one exit code.

uv run --env-file .env python -m ch15.cli --today 2026-01-15 "Which carriers ...?"
uv run python -m ch15.cli --demo carriers-late-last-quarter      # fake model, no key

Exit codes: 0 answered, 3 needs_info, 4 rejected (the final answer failed its checks after one
retry), 5 stopped (a budget limit or another StopCause), 2 bad arguments or configuration.
"""

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import ValidationError

from ch15.budget import RunBudget
from ch15.configs import ConfigError, load_configs, make_client
from ch15.fake_model import FakeModelClient
from ch15.golden import load_golden_tasks
from ch15.model_client import ModelClient
from ch15.pricing import Price
from ch15.research import ResearchResult, run_research
from ch15.scripted import DEMOS, FOLDER, ILLUSTRATIVE
from ch15.settings import Settings
from ch15.tools import (
    FixtureSearchBackend,
    HttpSearchBackend,
    SearchBackend,
    UnconfiguredSearch,
)
from ch15.trace import TraceRecorder

EXIT_ANSWERED, EXIT_USAGE, EXIT_NEEDS_INFO, EXIT_REJECTED, EXIT_STOPPED = 0, 2, 3, 4, 5
EXIT_CODES = {
    "answered": EXIT_ANSWERED,
    "needs_info": EXIT_NEEDS_INFO,
    "rejected": EXIT_REJECTED,
    "stopped": EXIT_STOPPED,
}
SEARCH_FIXTURE = FOLDER / "fixtures" / "search" / "carriers.json"


class StartupError(Exception):
    """A problem found before the run starts, reported in one line."""


def live_search(settings: Settings) -> SearchBackend:
    if not settings.search_endpoint:
        return UnconfiguredSearch()  # search_web stays in the tool set and says why
    if settings.search_api_key is None:
        raise StartupError("SEARCH_ENDPOINT is set but SEARCH_API_KEY is empty")
    return HttpSearchBackend(settings.search_endpoint, settings.search_api_key)


def check_exports(settings: Settings) -> None:
    folder = settings.exports_dir
    if not folder.is_dir() or not any(folder.glob("*.csv")):
        raise StartupError(f"no CSV exports in {folder}: run `uv run kestrel up --no-serve`")


def print_result(result: ResearchResult, price: Price | None, model_usd, out: Callable) -> None:
    run, answer = result.run, result.answer
    if result.outcome in ("answered", "needs_info") and answer is not None:
        out(f"{result.outcome.upper().replace('_', ' ')}  (confidence: {answer.confidence})")
        out(answer.answer)
        if answer.claims:
            out("Claims:")
            for i, claim in enumerate(answer.claims, 1):
                refs = "".join(f"[{c + 1}]" for c in claim.citations)
                out(f"  {i}. {claim.text} {refs}")
        if answer.citations:
            out("Citations:")
            for i, c in enumerate(answer.citations, 1):
                out(f"  [{i}] {c.location}  ({c.supports})")
        out("Missing: " + ("; ".join(answer.missing) or "-"))
    elif result.outcome == "rejected":
        out("REJECTED: the final answer failed its checks after one retry.")
        out("It is kept in the trace and not shown as an answer. Errors:")
        for error in run.answer_errors:
            out(f"  - {error}")
    else:
        out(f"STOPPED: {run.cause.value}. No answer; the trace has every step.")
    tokens_in = sum(s.input_tokens for s in run.steps)
    tokens_out = sum(s.output_tokens for s in run.steps)
    out("")
    out(
        f"Run: {run.cause.value} after {len(run.steps)} steps "
        f"(answer retries: {run.answer_retries}, searches: {result.search_calls})"
    )
    out(f"Tokens: {tokens_in:,} in / {tokens_out:,} out")
    model = "model unpriced (no price in models.toml)"
    if model_usd is not None:
        model = f"${model_usd:.4f} model ({price_label(price)})"
    search = "search unpriced (SEARCH_USD_PER_QUERY not set)"
    if result.search_usd is not None:
        search = f"${result.search_usd:.4f} search"
    out(f"Cost: {model} + {search}")


def price_label(price: Price | None) -> str:
    if price is ILLUSTRATIVE:
        return "illustrative price"
    return f"price as of {price.as_of}" if price else "unpriced"


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] = os.environ,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="?", help="the question (not with --demo)")
    parser.add_argument("--today", type=date.fromisoformat, help="the run's date, YYYY-MM-DD")
    parser.add_argument("--config", default="hosted-sdk", help="a configuration in models.toml")
    parser.add_argument("--models", type=Path, default=Path("models.toml"))
    parser.add_argument("--demo", choices=sorted(DEMOS), help="fake model, no key")
    parser.add_argument("--traces", type=Path, default=Path("traces") / "cli")
    args = parser.parse_args(argv)
    if bool(args.demo) == bool(args.question):
        parser.error("give a question or --demo NAME, not both")

    try:
        settings = Settings.from_env(env)
        check_exports(settings)
        client, backend, price, model_name, question, today = setup(args, settings, env)
    except ValidationError as exc:
        first = exc.errors()[0]
        out(f"error: {'.'.join(str(p) for p in first['loc'])}: {first['msg']}")
        return EXIT_USAGE
    except (StartupError, ConfigError, FileNotFoundError) as exc:
        out(f"error: {exc}")
        return EXIT_USAGE

    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%S%f}-{args.demo or 'question'}"
    budget = RunBudget(settings.run_max_steps, settings.run_max_tokens, settings.run_max_seconds)
    if args.demo:
        out(f"[demo {args.demo}: fake-model replies and token counts, hand-written search")
        out(" results, an illustrative price; tool results come from the seeded exports]")
    out(f"Question: {question}")
    out(f"Today: {today}")
    out("")
    with TraceRecorder(args.traces / f"{run_id}.jsonl", price) as trace:
        prompt = f"research_assistant_v{settings.prompt_version}"
        trace.run_start(run_id, question, today.isoformat(), model_name, budget, prompt)
        result = run_research(question, today, settings, client, backend, recorder=trace)
        trace.run_end(
            outcome=result.outcome,
            stop_cause=result.run.cause.value,
            steps=len(result.run.steps),
            total_tokens=result.run.total_tokens,
            answer_retries=result.run.answer_retries,
            answer_errors=result.run.answer_errors,
            citable=sorted(result.citable),
            search_calls=result.search_calls,
            model_usd=trace.model_usd,
            search_usd=result.search_usd,
            output=result.run.final_text,  # the last message, accepted or not
        )
    print_result(result, price, trace.model_usd, out)
    out(f"Trace: {trace.path}")
    return EXIT_CODES[result.outcome]


def setup(args: argparse.Namespace, settings: Settings, env: Mapping[str, str]) -> tuple:
    """(client, search backend, price, model name, question, today) for a demo or a live run."""
    if args.demo:
        demo = DEMOS[args.demo]
        task = next(t for t in load_golden_tasks() if t.id == demo.task_id)
        fixture = demo.search == "fixture"
        backend = FixtureSearchBackend(SEARCH_FIXTURE) if fixture else UnconfiguredSearch()
        client: ModelClient = FakeModelClient(demo.script())
        return client, backend, ILLUSTRATIVE, "fake", task.input, args.today or task.today
    if not args.models.is_file():
        raise StartupError(f"{args.models} not found: copy models.example.toml and fill it in")
    try:
        configs = {c.name: c for c in load_configs(args.models)}
    except ValidationError as exc:  # e.g. a SET-ME left in a price
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise StartupError(f"{args.models}: {loc}: {first['msg']}") from None
    if args.config not in configs:
        raise StartupError(f"no configuration {args.config!r} in {args.models}")
    config = configs[args.config]
    client = make_client(config, settings, env)  # ConfigError if .env lacks a value
    today = args.today or date.today()
    return client, live_search(settings), config.price, config.name, args.question, today


if __name__ == "__main__":
    sys.exit(main())
