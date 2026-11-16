"""Compare candidate configurations on the six Kestrel tasks: success, latency, tokens, cost.

uv run python -m ch11.compare_models          # every configuration in models.toml
uv run python -m ch11.compare_models --fake   # two scripted fake-model configurations, no key

Each run goes through Chapter 7's run_agent with the same prompt, tools and run budget.
Results go to results/results.csv (one row per run) and results/summary.txt.
"""

import argparse
import csv
import statistics
from collections.abc import Callable, Sequence
from decimal import Decimal
from pathlib import Path

import httpx
from pydantic import BaseModel

from ch11.agent import run_agent
from ch11.budget import CallLimits, RunBudget, StopCause
from ch11.configs import ConfigError, ModelConfig, load_configs, make_client
from ch11.kestrel_tools import build_compare_registry
from ch11.model_client import Message, ModelClient, ModelError
from ch11.pricing import run_cost
from ch11.prompts import load_prompt
from ch11.settings import Settings
from ch11.tasks import TASKS, Task, failure_label

ClientFor = Callable[[Task], ModelClient]  # one configuration's client, per task
Factory = Callable[[ModelConfig], ClientFor]  # raises ConfigError for a configuration it skips


class Row(BaseModel):
    config: str
    task_id: str
    run: int
    success: bool
    label: str  # "ok" or why the run failed
    cause: str  # Chapter 7's StopCause
    steps: int
    input_tokens: int
    output_tokens: int
    cost: Decimal | None  # None: unpriced
    wall_s: float
    invalid_args: int  # tool results that were argument validation errors


def preflight(client: ModelClient) -> None:
    """One tiny call before any task. A rejected request (wrong model name, an effort value
    the model doesn't accept, a bad key) is a configuration error, not a column of failures."""
    try:
        client.complete("", [Message(role="user", content="Reply with OK.")], max_tokens=64)
    except ModelError as exc:
        if exc.kind in ("auth", "bad_request"):
            raise ConfigError(f"preflight rejected: {exc}") from exc
        # timeouts and server errors: carry on; the runs record them as model_error


def real_clients(settings: Settings) -> Factory:
    def factory(config: ModelConfig) -> ClientFor:
        client = make_client(config, settings)  # raises ConfigError if .env lacks a value
        preflight(client)
        return lambda task: client  # stateless: one client serves every run

    return factory


def compare(
    configs: Sequence[ModelConfig],
    tasks: Sequence[Task],
    factory: Factory,
    api: httpx.Client,
    settings: Settings,
) -> tuple[list[Row], dict[str, str]]:
    system = load_prompt("compare", 1).body  # held constant across configurations
    budget = RunBudget(settings.run_max_steps, settings.run_max_tokens, settings.run_max_seconds)
    limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
    registry = build_compare_registry(api, settings.tool_result_max_chars)
    rows: list[Row] = []
    skipped: dict[str, str] = {}
    for config in configs:
        try:
            client_for = factory(config)
        except ConfigError as exc:
            skipped[config.name] = str(exc)
            continue
        for task in tasks:
            for run in range(1, settings.compare_runs + 1):  # sequential: no shared load
                result = run_agent(client_for(task), system, task.prompt, registry, budget, limits)
                label = failure_label(task, result, api)
                rows.append(
                    Row(
                        config=config.name,
                        task_id=task.task_id,
                        run=run,
                        success=label is None,
                        label=label or "ok",
                        cause=result.cause.value,
                        steps=len(result.steps),
                        input_tokens=sum(s.input_tokens for s in result.steps),
                        output_tokens=sum(s.output_tokens for s in result.steps),
                        cost=run_cost(result, config.price),
                        wall_s=round(result.elapsed_seconds, 2),
                        invalid_args=sum(
                            c.result_preview.startswith("Invalid arguments")
                            for s in result.steps
                            for c in s.tool_calls
                        ),
                    )
                )
    return rows, skipped


def summarise(rows: Sequence[Row], skipped: dict[str, str], show_wall: bool = True) -> str:
    lines = []
    for name in dict.fromkeys(r.config for r in rows):
        mine = [r for r in rows if r.config == name]
        wins = sum(r.success for r in mine)
        costs = [r.cost for r in mine]
        total = None if any(c is None for c in costs) else sum(costs, Decimal(0))
        walls = [r.wall_s for r in mine]
        mean_tokens = statistics.mean(r.input_tokens + r.output_tokens for r in mine)
        lines += [
            f"{name}",
            f"  success {wins}/{len(mine)}   finished {sum(r.cause == 'finished' for r in mine)}"
            f"   model_error {sum(r.cause == StopCause.MODEL_ERROR for r in mine)}"
            f"   invalid args {sum(r.invalid_args for r in mine)}",
            "  per task  "
            + "  ".join(
                f"{t} {sum(r.success for r in mine if r.task_id == t)}"
                f"/{sum(r.task_id == t for r in mine)}"
                for t in dict.fromkeys(r.task_id for r in mine)
            ),
            "  wall s    "
            + (
                f"median {statistics.median(walls):.1f}   slowest {max(walls):.1f}"
                if show_wall
                else "- (fake model: timing means nothing)"
            ),
            f"  tokens    mean {mean_tokens:.0f} per run",
            f"  cost      total {fmt(total)}   per success "
            + (fmt(total / wins) if total is not None and wins else "n/a"),
        ]
        reasons = sorted({r.label for r in mine if not r.success})
        if reasons:
            lines.append(f"  failures  {', '.join(reasons)}")
    lines += [f"{name}\n  skipped: {why}" for name, why in skipped.items()]
    return "\n".join(lines)


def fmt(amount: Decimal | None) -> str:
    return "unpriced" if amount is None else f"{amount:.4f} USD"


def write_results(rows: Sequence[Row], summary: str, out: Path) -> None:
    out.mkdir(exist_ok=True)
    with (out / "results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(Row.model_fields))
        writer.writeheader()
        writer.writerows(r.model_dump() for r in rows)
    (out / "summary.txt").write_text(summary + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare model configurations on Kestrel tasks.")
    parser.add_argument("--fake", action="store_true", help="scripted fake-model configurations")
    parser.add_argument("--models", type=Path, default=Path("models.toml"))
    args = parser.parse_args()
    settings = Settings.from_env()

    with httpx.Client(base_url=settings.kestrel_url, timeout=5.0) as api:  # tool calls: 5 s
        if args.fake:
            from ch11.scripted import FAKE_CONFIGS, fake_clients

            configs, factory = FAKE_CONFIGS, fake_clients(api, settings)
            print("[fake model: scripted replies and token counts; tool results from Kestrel]")
        else:
            configs, factory = load_configs(args.models), real_clients(settings)
        rows, skipped = compare(configs, TASKS, factory, api, settings)

    summary = summarise(rows, skipped, show_wall=not args.fake)
    write_results(rows, summary, Path("results"))
    print(summary)
    expected = (len(configs) - len(skipped)) * len(TASKS) * settings.compare_runs
    print(f"{len(rows)} rows written to results/results.csv (expected {expected})")


if __name__ == "__main__":
    main()
