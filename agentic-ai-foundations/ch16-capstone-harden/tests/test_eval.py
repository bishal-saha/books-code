"""The offline eval: trials, the eval-wide cap, Chapter 13's trace layout and the report."""

from decimal import Decimal
from pathlib import Path

from ch16.eval import format_report, offline_setup, run_eval, summarise
from ch16.golden import load_golden_tasks
from ch16.scripted import ILLUSTRATIVE, ILLUSTRATIVE_SEARCH_USD
from ch16.settings import Settings

TASKS = load_golden_tasks()


def settings(exports: Path, cap: str = "0.50") -> Settings:
    return Settings(
        exports_dir=exports,
        search_usd_per_query=ILLUSTRATIVE_SEARCH_USD,
        eval_max_cost_usd=Decimal(cap),
    )


def evaluate(exports: Path, traces: Path, trials: int = 5, cap: str = "0.50"):
    s = settings(exports, cap)
    return run_eval(TASKS, offline_setup, s, ILLUSTRATIVE, trials, traces, "fake", lambda x: None)


def test_every_task_passes_every_offline_trial(exports: Path, tmp_path: Path) -> None:
    results, spent = evaluate(exports, tmp_path)
    assert len(results) == 30 and all(r.status == "passed" for r in results)
    rows = {r.task_id: r for r in summarise(results, [t.id for t in TASKS])}
    carriers = rows["carriers-late-last-quarter"]
    assert carriers.max_cost == Decimal("0.0253")  # trials 2 and 4: one 503, one more request
    assert carriers.avg_cost == Decimal("0.0223")
    assert rows["carriers-tight-money"].stop_causes == {"cost_limit": 5}
    assert spent == Decimal("0.3395")


def test_traces_use_chapter_13s_layout(exports: Path, tmp_path: Path) -> None:
    evaluate(exports, tmp_path, trials=2)
    (eval_dir,) = tmp_path.iterdir()  # one eval id per eval
    names = sorted(p.name for p in eval_dir.glob("*.jsonl"))
    assert len(names) == 12 and "sandbox-probe-t2.jsonl" in names


def test_the_eval_cap_skips_trials_evenly(exports: Path, tmp_path: Path) -> None:
    results, spent = evaluate(exports, tmp_path, trials=5, cap="0.10")
    skipped = [r for r in results if r.status == "skipped"]
    assert skipped and spent < Decimal("0.10") + Decimal("0.0253")  # over by one trial at most
    assert {r.trial for r in skipped} == {2, 3, 4, 5}


def test_the_report_has_one_row_per_task(exports: Path, tmp_path: Path) -> None:
    results, spent = evaluate(exports, tmp_path, trials=1)
    report = format_report(summarise(results, [t.id for t in TASKS]), spent, Decimal("0.50"))
    lines = report.splitlines()
    assert lines[0].startswith("task") and lines[-1].startswith("overall")
    assert len(lines) == 2 + len(TASKS)
