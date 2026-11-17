"""The capstone's golden tasks: Chapter 13's format, plus a date, a status, citations and counts.

Copied from Chapter 14. New in Chapter 15: grade(), which checks one run against its task.

Expected counts are never typed in: resolve_count reads the export with the csv module, apart
from the agent's own count_rows, so a bug in that tool can't make its own test pass.
"""

import csv
import json
import tomllib
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ch15.tools import SearchResult

if TYPE_CHECKING:
    from ch15.research import ResearchResult

FOLDER = Path(__file__).resolve().parent.parent
GOLDEN_TASKS = FOLDER / "golden_tasks.toml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a misspelt field is an error, not ignored


class ToolExpectation(Strict):  # Chapter 13
    tool: str
    args: dict[str, object] = {}  # a subset: other arguments are allowed


class CountFact(Strict):
    """A count the answer must contain, computed from the export when the task is loaded."""

    file: str
    where: dict[str, str] = {}
    date_column: str
    date_from: date  # inclusive
    date_to: date  # exclusive
    group_by: str | None = None
    top: int | None = Field(default=None, gt=0)  # with group_by: the largest groups


class ExpectedCitations(Strict):
    files: list[str] = []  # each must be cited
    urls_from: str | None = None  # hand-written search fixture; every URL cited must be in it


class GoldenTask(Strict):
    id: str
    input: str
    today: date  # the run's date: "last quarter" is relative to it
    required_tool_calls: list[ToolExpectation] = []
    forbidden_tool_calls: list[ToolExpectation] = []
    count_facts: list[CountFact] = []
    expected_status: Literal["answered", "needs_info"]
    expected_citations: ExpectedCitations = ExpectedCitations()
    max_steps: int = Field(gt=0)

    @model_validator(mode="after")
    def refusals_cite_nothing(self) -> "GoldenTask":
        refusal = self.expected_status == "needs_info"
        if refusal and (self.count_facts or self.expected_citations.files):
            raise ValueError(f"{self.id}: a needs_info task expects no facts or citations")
        return self


def load_golden_tasks(path: Path = GOLDEN_TASKS) -> list[GoldenTask]:
    with path.open("rb") as f:
        tasks = [GoldenTask(**entry) for entry in tomllib.load(f)["task"]]
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("golden task ids must be unique")
    return tasks


def resolve_count(fact: CountFact, exports: Path) -> list[tuple[str | None, int]]:
    """(group, count) pairs, largest first; one (None, count) pair without group_by."""
    counts: dict[str | None, int] = {}
    with (exports / fact.file).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cell = row[fact.date_column]
            if not cell or not fact.date_from <= date.fromisoformat(cell[:10]) < fact.date_to:
                continue
            if all(row[col] == value for col, value in fact.where.items()):
                key = row[fact.group_by] if fact.group_by else None
                counts[key] = counts.get(key, 0) + 1
    if fact.group_by is None:
        return [(None, counts.get(None, 0))]
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[: fact.top] if fact.top else ranked


def search_fixture(name: str) -> dict[str, list[SearchResult]]:
    """A hand-written search fixture, keyed by the subject searched for."""
    data = json.loads((FOLDER / name).read_text(encoding="utf-8"))
    return {k: [SearchResult(**r) for r in v] for k, v in data["results"].items()}


# --- New in Chapter 15: grading one run against its golden task, without a model ---


def grade(task: GoldenTask, result: "ResearchResult", exports: Path) -> list[str]:
    """The reasons a run fails its task; an empty list is a pass. Deterministic checks only."""
    failures = []
    if result.outcome != task.expected_status:
        failures.append(f"outcome {result.outcome}, expected {task.expected_status}")
    calls = [c for s in result.run.steps for c in s.tool_calls]

    def seen(exp: ToolExpectation) -> bool:
        return any(
            c.name == exp.tool and all(c.arguments.get(k) == v for k, v in exp.args.items())
            for c in calls
        )

    failures += [f"missing call: {e.tool}" for e in task.required_tool_calls if not seen(e)]
    failures += [f"forbidden call: {e.tool}" for e in task.forbidden_tool_calls if seen(e)]
    if len(result.run.steps) > task.max_steps:
        failures.append(f"{len(result.run.steps)} steps, more than {task.max_steps}")

    answer = result.answer
    claims = " ".join(c.text for c in answer.claims) if answer else ""
    for fact in task.count_facts:  # every expected count, next to its group, in a claim
        for group, count in resolve_count(fact, exports):
            if str(count) not in claims or (group and group not in claims):
                failures.append(f"missing fact: {group or fact.file} {count}")
    cited = {c.location for c in answer.citations} if answer else set()
    failures += [f"not cited: {f}" for f in task.expected_citations.files if f not in cited]
    if task.expected_citations.urls_from:
        fixture = search_fixture(task.expected_citations.urls_from)
        allowed = {r.url for results in fixture.values() for r in results}
        urls = [u for u in cited if u.startswith(("https://", "http://"))]
        failures += [f"url not in fixture: {u}" for u in urls if u not in allowed]
    return failures
