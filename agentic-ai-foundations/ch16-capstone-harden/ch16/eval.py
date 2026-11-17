"""Chapter 13's eval, run over the research assistant: every golden task, several trials each.

uv run python -m ch16.eval                                    # fake model, no key, no network
uv run --env-file .env python -m ch16.eval --live --config hosted-sdk

Copied from Chapter 13 (ch13/eval.py) and pointed at run_research and Chapter 15's grade():
trials run trial-major, each with a fresh run budget and its own trace at
traces/<eval_id>/<task_id>-t<trial>.jsonl; EVAL_MAX_COST_USD caps the whole eval; a trial's
status (passed, failed, error, skipped) is separate from the run's StopCause.
New in Chapter 16: cost includes search requests, the report adds the most expensive trial, and
offline trials 2 and 4 get a search service whose first request fails with HTTP 503, so the
report shows what retries cost. Offline results are fake-model output: they test the harness
and the failure handling, not a model.
"""

import argparse
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ch16.budget import RunBudget
from ch16.cli import StartupError, check_exports, live_search
from ch16.configs import ConfigError, load_configs, make_client
from ch16.fake_model import FakeModelClient
from ch16.golden import GoldenTask, grade, load_golden_tasks
from ch16.model_client import ModelClient
from ch16.offline import OfflineSearchService
from ch16.pricing import Price
from ch16.research import run_research
from ch16.scripted import DEMOS, ILLUSTRATIVE, ILLUSTRATIVE_SEARCH_USD
from ch16.settings import Settings
from ch16.tools import SearchBackend
from ch16.trace import TraceRecorder

FAULTY_TRIALS = {2, 4}  # offline only: the search service answers 503 to its first request
SetupFor = Callable[[GoldenTask, int], tuple[ModelClient, SearchBackend]]


class TrialResult(BaseModel):
    task_id: str
    trial: int
    status: Literal["passed", "failed", "error", "skipped"]  # a trial status, not a StopCause
    stop_cause: str | None = None  # Chapter 7's StopCause; None when the run never ended
    steps: int = 0
    cost_usd: Decimal = Decimal(0)  # model and search together
    failures: list[str] = []  # the reasons of the failed checks, or the error


def offline_setup(task: GoldenTask, trial: int) -> tuple[ModelClient, SearchBackend]:
    """Fake-model script for the task; the offline search service, faulty on some trials."""
    statuses = [503] if trial in FAULTY_TRIALS else []
    return FakeModelClient(DEMOS[task.id].script()), OfflineSearchService(statuses).backend()


def run_trial(
    task: GoldenTask,
    trial: int,
    setup_for: SetupFor,
    settings: Settings,
    price: Price,
    trace_path: Path,
    model_name: str,
    sleep: Callable[[float], None],
) -> TrialResult:
    if task.run_max_cost_usd is not None:  # a task may set its own money budget
        settings = settings.model_copy(update={"run_max_cost_usd": task.run_max_cost_usd})
    budget = RunBudget(
        settings.run_max_steps,
        settings.run_max_tokens,
        settings.run_max_seconds,
        settings.run_max_cost_usd,
    )
    trace = TraceRecorder(trace_path, price)
    try:
        client, backend = setup_for(task, trial)
        with trace:
            prompt = f"research_assistant_v{settings.prompt_version}"
            trace.run_start(trace_path.stem, task.input, task.today.isoformat(), model_name,
                            budget, prompt)  # fmt: skip
            result = run_research(
                task.input, task.today, settings, client, backend, price, trace, sleep=sleep
            )
            trace.run_end(
                outcome=result.outcome,
                stop_cause=result.run.cause.value,
                stop_detail=result.run.stop_detail,
                steps=len(result.run.steps),
                search_requests=result.search_requests,
                model_usd=result.model_usd,
                search_usd=result.search_usd,
            )
        failures = grade(task, result, settings.exports_dir)
    except Exception as exc:  # one broken trial must not end the eval
        error = f"error: {type(exc).__name__}: {exc}"
        spent = trace.model_usd or Decimal(0)  # the model calls it made before it broke
        return TrialResult(
            task_id=task.id, trial=trial, status="error", cost_usd=spent, failures=[error]
        )
    return TrialResult(
        task_id=task.id,
        trial=trial,
        status="failed" if failures else "passed",
        stop_cause=result.run.cause.value,
        steps=len(result.run.steps),
        cost_usd=(result.model_usd or 0) + (result.search_usd or 0),
        failures=failures,
    )


def run_eval(
    tasks: Sequence[GoldenTask],
    setup_for: SetupFor,
    settings: Settings,
    price: Price,
    trials: int,
    traces_dir: Path,
    model_name: str,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[TrialResult], Decimal]:
    eval_dir = traces_dir / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")  # the eval id
    results: list[TrialResult] = []
    spent = Decimal(0)
    for trial in range(1, trials + 1):  # trial-major: a cap hit thins every task evenly
        for task in tasks:
            if spent >= settings.eval_max_cost_usd:
                skipped = TrialResult(
                    task_id=task.id, trial=trial, status="skipped", failures=["eval cap reached"]
                )
                results.append(skipped)
                continue
            path = eval_dir / f"{task.id}-t{trial}.jsonl"
            result = run_trial(task, trial, setup_for, settings, price, path, model_name, sleep)
            results.append(result)
            spent += result.cost_usd
    return results, spent


# --- The report ---


class TaskRow(BaseModel):
    task_id: str
    ran: int  # passed + failed + error; skipped trials are not in the denominator
    passed: int
    skipped: int
    avg_cost: Decimal
    max_cost: Decimal  # new in Chapter 16
    avg_steps: float
    stop_causes: dict[str, int]
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
        ended = [r for r in ran if r.status != "error"]
        costs = [r.cost_usd for r in ran] or [Decimal(0)]
        failures = Counter(f for r in ran for f in r.failures)
        rows.append(
            TaskRow(
                task_id=task_id,
                ran=len(ran),
                passed=sum(r.status == "passed" for r in ran),
                skipped=len(mine) - len(ran),
                avg_cost=sum(costs) / len(costs),
                max_cost=max(costs),
                avg_steps=sum(r.steps for r in ended) / len(ended) if ended else 0.0,
                stop_causes=dict(Counter(r.stop_cause for r in ended if r.stop_cause)),
                top_failure=failures.most_common(1)[0][0] if failures else "-",
            )
        )
    return rows


def format_report(rows: Sequence[TaskRow], spent: Decimal, cap: Decimal) -> str:
    lines = [
        f"{'task':<28} {'pass':<5} {'pass^k':<7} {'avg cost':<9} {'max cost':<9} "
        f"{'avg steps':<9} stop causes"
    ]
    for r in rows:
        causes = " ".join(f"{c}={n}" for c, n in sorted(r.stop_causes.items()))
        lines.append(
            f"{r.task_id:<28} {f'{r.passed}/{r.ran}':<5} {'yes' if r.pass_hat_k else 'no':<7} "
            f"${r.avg_cost:<8.4f} ${r.max_cost:<8.4f} {r.avg_steps:<9.1f} {causes}"
        )
        if r.top_failure != "-":
            lines.append(f"{'':<28} top failure: {r.top_failure}")
    ran, passed = sum(r.ran for r in rows), sum(r.passed for r in rows)
    skipped = sum(r.skipped for r in rows)
    lines.append(
        f"{'overall':<28} {f'{passed}/{ran}':<5} "
        f"{f'{sum(r.pass_hat_k for r in rows)}/{len(rows)}':<7} "
        f"spent ${spent:.4f} of the ${cap:.2f} eval cap, {skipped} skipped"
    )
    return "\n".join(lines)


def live_setup(args: argparse.Namespace, settings: Settings) -> tuple[SetupFor, Price, str]:
    configs = {c.name: c for c in load_configs(args.models)}
    if args.config not in configs:
        raise StartupError(f"--live needs --config, one of: {', '.join(configs)}")
    config = configs[args.config]
    if config.price is None:  # an unpriced run would cost "zero" and no cap would ever fire
        raise ConfigError("an eval needs a price: its budgets are in money")
    client = make_client(config, settings)  # ConfigError if .env lacks a value
    backend = live_search(settings)
    return (lambda task, trial: (client, backend)), config.price, config.name


def main(argv: Sequence[str] | None = None, out: Callable[[str], None] = print) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=None, help="default: EVAL_TRIALS")
    parser.add_argument("--live", action="store_true", help="use a real model (your key)")
    parser.add_argument("--config", help="with --live: a configuration name in models.toml")
    parser.add_argument("--models", type=Path, default=Path("models.toml"))
    parser.add_argument("--traces", type=Path, default=Path("traces"))
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    try:
        check_exports(settings)
        if args.live:
            setup_for, price, model_name = live_setup(args, settings)
        else:
            out("[fake model: scripted replies and token counts, hand-written search results,")
            out(" illustrative prices; tool results come from the seeded exports]")
            settings = settings.model_copy(update={"search_usd_per_query": ILLUSTRATIVE_SEARCH_USD})
            setup_for, price, model_name = offline_setup, ILLUSTRATIVE, "fake"
    except (StartupError, ConfigError, FileNotFoundError) as exc:
        out(f"error: {exc}")
        return 2
    tasks = load_golden_tasks()
    trials = args.trials or settings.eval_trials
    results, spent = run_eval(tasks, setup_for, settings, price, trials, args.traces, model_name)
    rows = summarise(results, [t.id for t in tasks])
    out(format_report(rows, spent, settings.eval_max_cost_usd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
