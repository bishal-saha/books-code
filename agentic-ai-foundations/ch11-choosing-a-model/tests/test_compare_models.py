"""The harness end to end with two scripted fake-model configurations and the seeded API."""

import httpx
import pytest
from ch11.compare_models import compare, summarise
from ch11.scripted import FAKE_CONFIGS, fake_clients
from ch11.settings import Settings
from ch11.tasks import TASKS


@pytest.fixture(scope="module")
def outcome(kestrel_url: str):
    settings = Settings(compare_runs=2)
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as api:
        rows, skipped = compare(FAKE_CONFIGS, TASKS, fake_clients(api, settings), api, settings)
    return rows, skipped


def test_one_row_per_run_and_the_skip_is_reported(outcome) -> None:
    rows, skipped = outcome
    assert len(rows) == 2 * len(TASKS) * 2  # two configurations ran
    assert list(skipped) == ["local-server"]
    assert skipped["local-server"].startswith("not configured")


def test_stop_cause_alone_cannot_tell_them_apart(outcome) -> None:
    rows, _ = outcome
    assert all(r.cause == "finished" for r in rows)
    correct = [r for r in rows if r.config == "fake-correct"]
    wrong = [r for r in rows if r.config == "fake-wrong-tool"]
    assert all(r.success for r in correct)
    assert {r.label for r in wrong} == {"no required tool call"}
    assert sum(r.cost for r in correct) == sum(r.cost for r in wrong)  # same cost per run


def test_summary_shows_cost_per_success(outcome) -> None:
    rows, skipped = outcome
    summary = summarise(rows, skipped, show_wall=False)
    print(summary)  # pytest -s shows it: fake-model output
    assert "per success 0.0037 USD" in summary
    assert "per success n/a" in summary
    assert "local-server\n  skipped: not configured" in summary
