"""The eval runner on the fake model: counts, the cost cap, and a trial that crashes."""

from decimal import Decimal

from ch13.eval import format_report, run_eval, summarise
from ch13.golden import load_golden_tasks
from ch13.scripted import ILLUSTRATIVE, fake_client_for
from ch13.settings import Settings

TASKS = load_golden_tasks()
IDS = [t.id for t in TASKS]


def run(registry, tmp_path, settings=None, client_for=fake_client_for, trials=5):
    settings = settings or Settings()
    return run_eval(TASKS, client_for, registry, settings, ILLUSTRATIVE, trials, tmp_path, "fake")


def test_the_scripted_eval_counts_passes_and_failures(registry, tmp_path):
    results, spent = run(registry, tmp_path)
    rows = {r.task_id: r for r in summarise(results, IDS)}
    assert (rows["late-top-carrier-needs-info"].passed, rows["stock-total"].passed) == (3, 4)
    assert rows["late-top-carrier-needs-info"].top_failure == "missing fact: NEEDS INFO"
    assert rows["stock-total"].stop_causes == {"finished": 4, "step_limit": 1}
    assert sum(r.pass_at_k for r in rows.values()) == 6
    assert sum(r.pass_hat_k for r in rows.values()) == 4
    assert len(list(tmp_path.rglob("*.jsonl"))) == 30  # one trace per trial
    assert spent > 0


def test_the_cost_cap_skips_trials_evenly(registry, tmp_path):
    settings = Settings(eval_max_cost_usd=Decimal("0.02"))
    results, _ = run(registry, tmp_path, settings)
    rows = summarise(results, IDS)
    assert all(r.skipped > 0 for r in rows)  # trial-major: every task loses trials
    assert all(r.ran >= 1 for r in rows)
    assert "skipped" in format_report(rows, 5, Decimal("0.02"), Decimal("0.02"))


def test_a_crashing_trial_is_an_error_not_a_stop_cause(registry, tmp_path):
    def client_for(task, trial):
        client = fake_client_for(task, trial)
        if task.id == "order-status" and trial == 1:
            client._script = client._script[:1]  # the script runs out: ScriptExhausted
        return client

    results, _ = run(registry, tmp_path, client_for=client_for, trials=2)
    broken = next(r for r in results if r.task_id == "order-status" and r.trial == 1)
    assert broken.status == "error" and broken.stop_cause is None
    assert broken.failures[0].startswith("error: ScriptExhausted")
    row = next(r for r in summarise(results, IDS) if r.task_id == "order-status")
    assert (row.passed, row.ran, row.errors) == (1, 2, 1)
