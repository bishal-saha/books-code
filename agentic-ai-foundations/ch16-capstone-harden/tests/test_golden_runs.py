"""The offline golden tasks: each task's fake-model script, run end to end and graded.

The scripts are fake-model output; the counts, the sandbox and the citation checks are real.
"""

from pathlib import Path

import pytest
from ch16.cli import demo_backend
from ch16.fake_model import FakeModelClient
from ch16.golden import grade, load_golden_tasks
from ch16.research import run_research
from ch16.scripted import DEMOS, ILLUSTRATIVE, ILLUSTRATIVE_SEARCH_USD
from ch16.settings import Settings

TASKS = {t.id: t for t in load_golden_tasks()}


def research(demo_name: str, exports: Path):
    """One demo run, priced like the CLI's demos, with no real sleeps between retries."""
    demo = DEMOS[demo_name]
    task = TASKS[demo.task_id]
    settings = Settings(exports_dir=exports, search_usd_per_query=ILLUSTRATIVE_SEARCH_USD)
    if task.run_max_cost_usd:
        settings = settings.model_copy(update={"run_max_cost_usd": task.run_max_cost_usd})
    client = FakeModelClient(demo.script())
    result = run_research(
        task.input, task.today, settings, client, demo_backend(demo), ILLUSTRATIVE,
        sleep=lambda s: None,
    )  # fmt: skip
    return task, result


@pytest.mark.parametrize("task_id", sorted(TASKS))
def test_every_golden_task_passes_offline(task_id: str, exports: Path) -> None:
    task, result = research(task_id, exports)
    assert grade(task, result, exports) == []


def test_the_grader_catches_a_rejected_run(exports: Path) -> None:
    task, result = research("invented-url-rejected", exports)
    assert result.outcome == "rejected"
    assert grade(task, result, exports)[0] == "outcome rejected, expected answered"


def test_the_grader_catches_a_wrong_count(exports: Path) -> None:
    task, result = research("carriers-late-last-quarter", exports)
    claim = result.answer.claims[0]
    claim.text = claim.text.replace("139", "193")
    assert grade(task, result, exports) == ["missing fact: Harbour Express 139"]


def test_a_partial_answer_is_answered_with_missing(exports: Path) -> None:
    task, result = research("no-search-partial", exports)
    assert result.outcome == "answered" and result.answer.missing
    assert result.citable == {"shipments.csv"}  # the failed searches made nothing citable
