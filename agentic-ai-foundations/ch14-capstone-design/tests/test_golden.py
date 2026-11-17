"""The golden tasks load, and their expected counts match the seeded exports."""

from datetime import date
from pathlib import Path

from ch14.golden import load_golden_tasks, resolve_count, search_fixture
from ch14.tools import CountRowsArgs

TASKS = {t.id: t for t in load_golden_tasks()}


def test_five_tasks_and_both_statuses() -> None:
    assert len(TASKS) == 5
    assert {t.expected_status for t in TASKS.values()} == {"answered", "needs_info"}


def test_expected_counts_from_the_seeded_data(exports: Path) -> None:
    def counts(task_id: str) -> list:
        return resolve_count(TASKS[task_id].count_facts[0], exports)

    assert counts("carriers-late-last-quarter") == [
        ("Harbour Express", 139),
        ("Swiftway Parcel", 93),
    ]
    assert counts("lost-by-one-carrier") == [(None, 13)]
    assert counts("zero-in-a-covered-month") == [(None, 0)]


def test_the_uncovered_quarter_has_no_rows(exports: Path) -> None:
    fact = (
        TASKS["carriers-late-last-quarter"]
        .count_facts[0]
        .model_copy(update={"where": {}, "group_by": None, "top": None})
    )
    q2 = fact.model_copy(update={"date_from": date(2026, 4, 1), "date_to": date(2026, 7, 1)})
    assert resolve_count(q2, exports) == [(None, 0)]


def test_counts_are_expressible_with_count_rows() -> None:
    """Each fact is a count the agent's own tool can ask for: same fields, same meaning."""
    for task in TASKS.values():
        for fact in task.count_facts:
            CountRowsArgs(path=fact.file, **fact.model_dump(exclude={"file", "top"}))


def test_search_fixture_is_valid() -> None:
    results = search_fixture(TASKS["carriers-late-last-quarter"].expected_citations.urls_from)
    assert set(results) == {"Harbour Express", "Swiftway Parcel"}
    assert all(r.url.startswith("https://") for rs in results.values() for r in rs)
