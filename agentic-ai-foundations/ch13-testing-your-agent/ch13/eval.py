"""A small local eval: every golden task, several trials each, graded from the trace.

uv run python -m ch13.eval                          # fake model, scripted replies, no key
uv run python -m ch13.eval --live --config NAME     # a configuration from models.toml

Each trial is a fresh run with its own trace file and run budget. The report gives pass rate,
pass@k, pass^k, average cost and average steps per task. EVAL_MAX_COST_USD caps the whole eval.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel

from ch13.agent import run_agent
from ch13.budget import CallLimits, RunBudget
from ch13.configs import ConfigError, Price, load_configs, make_client
from ch13.golden import GoldenTask, check_tool_names, load_golden_tasks
from ch13.grading import grade
from ch13.kestrel_tools import build_ops_registry
from ch13.model_client import ModelClient
from ch13.prompts import load_prompt
from ch13.scripted import ILLUSTRATIVE, fake_client_for
from ch13.settings import Settings
from ch13.tools import ToolRegistry
from ch13.trace import TraceRecorder, read_trace

ClientFor = Callable[[GoldenTask, int], ModelClient]  # a fresh client per task and trial


class TrialResult(BaseModel):
    task_id: str
    trial: int
    status: Literal["graded", "error", "skipped"]  # a trial outcome, not a StopCause
    passed: bool = False
    stop_cause: str | None = None  # Chapter 7's StopCause; None when the run never ended
    steps: int = 0
    cost_usd: Decimal | None = None
    failures: list[str] = []  # the reasons of the failed checks, or the error


def run_trial(
    task: GoldenTask,
    trial: int,
    client: ModelClient,
    registry: ToolRegistry,
    settings: Settings,
    price: Price | None,
    trace_path: Path,
    model_name: str,
) -> tuple[TrialResult, Decimal | None]:
    budget = RunBudget(task.max_steps, settings.run_max_tokens, settings.run_max_seconds)
    limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
    prompt = load_prompt("operations", settings.prompt_version)
    recorder = TraceRecorder(trace_path, price)
    try:
        with recorder:
            recorder.run_start(
                trace_path.stem, task.id, f"{prompt.name}_v{prompt.version}", model_name, budget
            )
            run_agent(client, prompt.body, task.input, registry, budget, limits, recorder=recorder)
        events = read_trace(trace_path)
        checks = grade(task, events)
    except Exception as exc:  # one broken trial must not end the eval
        error = f"error: {type(exc).__name__}: {exc}"
        failed = TrialResult(task_id=task.id, trial=trial, status="error", failures=[error])
        return failed, recorder.cost_usd  # what it spent before it broke still counts
    run_end = events[-1]
    return TrialResult(
        task_id=task.id,
        trial=trial,
        status="graded",
        passed=all(c.passed for c in checks),
        stop_cause=run_end["stop_cause"],
        steps=run_end["steps"],
        cost_usd=recorder.cost_usd,
        failures=[c.reason for c in checks if not c.passed],
    ), recorder.cost_usd


def run_eval(
    tasks: Sequence[GoldenTask],
    client_for: ClientFor,
    registry: ToolRegistry,
    settings: Settings,
    price: Price | None,
    trials: int,
    traces_dir: Path,
    model_name: str,
) -> tuple[list[TrialResult], Decimal]:
    if price is None:  # an unpriced run would cost "zero" and the cap would never fire
        raise ConfigError("an eval needs a price: its cost cap is in money")
    check_tool_names(list(tasks), {d.name for d in registry.definitions()})
    eval_dir = traces_dir / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    results: list[TrialResult] = []
    spent = Decimal(0)
    for trial in range(1, trials + 1):  # trial-major: a cap hit thins every task evenly
        for task in tasks:
            if spent >= settings.eval_max_cost_usd:
                results.append(
                    TrialResult(
                        task_id=task.id,
                        trial=trial,
                        status="skipped",
                        failures=["eval cost cap reached"],
                    )
                )
                continue
            trace_path = eval_dir / f"{task.id}-t{trial}.jsonl"
            client = client_for(task, trial)
            result, cost = run_trial(
                task, trial, client, registry, settings, price, trace_path, model_name
            )
            results.append(result)
            spent += cost or 0
    return results, spent


# --- The report ---


class TaskRow(BaseModel):
    task_id: str
    ran: int  # graded + error; skipped trials are not in the denominator
    passed: int
    skipped: int
    avg_cost: Decimal | None
    avg_steps: float
    stop_causes: dict[str, int]
    errors: int
    top_failure: str

    @property
    def pass_at_k(self) -> bool:  # any trial passed: the agent CAN do it
        return self.passed > 0

    @property
    def pass_hat_k(self) -> bool:  # every trial passed: the agent DOES do it, each time
        return self.ran > 0 and self.passed == self.ran


def summarise(results: Sequence[TrialResult], task_ids: Sequence[str]) -> list[TaskRow]:
    rows = []
    for task_id in task_ids:
        mine = [r for r in results if r.task_id == task_id]
        ran = [r for r in mine if r.status != "skipped"]
        graded = [r for r in ran if r.status == "graded"]
        costs = [r.cost_usd for r in ran if r.cost_usd is not None]
        failures = Counter(f for r in ran for f in r.failures)
        rows.append(
            TaskRow(
                task_id=task_id,
                ran=len(ran),
                passed=sum(r.passed for r in ran),
                skipped=len(mine) - len(ran),
                avg_cost=sum(costs) / len(costs) if costs else None,
                avg_steps=sum(r.steps for r in graded) / len(graded) if graded else 0.0,
                stop_causes=dict(Counter(r.stop_cause for r in graded if r.stop_cause)),
                errors=len(ran) - len(graded),
                top_failure=failures.most_common(1)[0][0] if failures else "-",
            )
        )
    return rows


def format_report(rows: Sequence[TaskRow], trials: int, spent: Decimal, cap: Decimal) -> str:
    def money(value: Decimal | None) -> str:
        return "-" if value is None else f"${value:.4f}"

    lines = [
        f"{'task':<28} {'pass':<6} {'pass@k':<7} {'pass^k':<7} {'avg cost':<9} "
        f"{'avg steps':<10} {'stop causes':<24} top failure"
    ]
    for r in rows:
        k = f"{r.ran}/{trials}" if r.skipped else ""  # fewer than k trials ran
        causes = " ".join(f"{c}={n}" for c, n in sorted(r.stop_causes.items()))
        if r.errors:
            causes += f" errors={r.errors}"
        lines.append(
            f"{r.task_id:<28} {f'{r.passed}/{r.ran}':<6} {'yes' if r.pass_at_k else 'no':<7} "
            f"{('yes' if r.pass_hat_k else 'no') + k:<7} {money(r.avg_cost):<9} "
            f"{r.avg_steps:<10.1f} {causes:<24} {r.top_failure}"
        )
    ran, passed = sum(r.ran for r in rows), sum(r.passed for r in rows)
    skipped = sum(r.skipped for r in rows)
    lines.append(
        f"{'overall':<28} {f'{passed}/{ran}':<6} "
        f"{f'{sum(r.pass_at_k for r in rows)}/{len(rows)}':<7} "
        f"{f'{sum(r.pass_hat_k for r in rows)}/{len(rows)}':<7} "
        f"spent ${spent:.4f} of ${cap:.2f} cap, {skipped} skipped"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=None, help="default: EVAL_TRIALS")
    parser.add_argument("--live", action="store_true", help="use a real model (your key)")
    parser.add_argument("--config", help="with --live: a configuration name in models.toml")
    parser.add_argument("--models", type=Path, default=Path("models.toml"))
    parser.add_argument("--traces", type=Path, default=Path("traces"))
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    trials = args.trials or settings.eval_trials
    tasks = load_golden_tasks()

    if args.live:
        configs = {c.name: c for c in load_configs(args.models)}
        if args.config not in configs:
            parser.error(f"--live needs --config, one of: {', '.join(configs)}")
        config = configs[args.config]
        live = make_client(config, settings)  # raises ConfigError if .env lacks a value
        client_for: ClientFor = lambda task, trial: live  # noqa: E731 (stateless client)
        price, model_name = config.price, config.name
    else:
        print("[fake model: scripted replies and token counts; tool results from Kestrel]")
        client_for, price, model_name = fake_client_for, ILLUSTRATIVE, "fake"

    with httpx.Client(base_url=settings.kestrel_url, timeout=10.0) as http:
        try:
            http.get("/health").raise_for_status()
        except httpx.HTTPError:
            print(f"Kestrel is not answering at {settings.kestrel_url}: run `uv run kestrel up`")
            return 2
        registry = build_ops_registry(http, settings.tool_result_max_chars)
        results, spent = run_eval(
            tasks, client_for, registry, settings, price, trials, args.traces, model_name
        )
    rows = summarise(results, [t.id for t in tasks])
    print(format_report(rows, trials, spent, settings.eval_max_cost_usd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
