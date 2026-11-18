"""The research assistant's four read-only tools: contracts now, bodies in Chapter 15.

Each tool follows Chapter 8: a verb-first name, a description that says when (and when not)
to use it, a strict pydantic input model that generates the JSON Schema, a fixed output
shape, and errors written for the model. Every function takes its validated arguments only;
build_registry binds the rest (sandbox root, search backend, timeout) with functools.partial.
"""

from collections.abc import Callable
from datetime import date
from functools import partial
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ch14.registry import Tool, ToolRegistry
from ch14.sandbox import SandboxError, resolve_in_sandbox
from ch14.truncate import ProvenancedResult

SEARCH_MAX_RESULTS = 10
TITLE_MAX_CHARS = 200
URL_MAX_CHARS = 500  # longer URLs are dropped, never cut: a cut URL can't be cited
SNIPPET_MAX_CHARS = 300
READ_FILE_MAX_CHARS = 6_000
MAX_EXPRESSION_CHARS = 200
HEADER_MAX_CHARS = 300  # a header row longer than this is cut in the description


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")  # an unknown argument is an error, not ignored


# --- search_web: outside opinion, as titles, URLs and snippets ---


class SearchWebArgs(StrictArgs):
    query: str = Field(min_length=3, max_length=200, description="Search terms")
    max_results: int = Field(default=5, ge=1, le=SEARCH_MAX_RESULTS)


class SearchResult(BaseModel):
    title: str = Field(max_length=TITLE_MAX_CHARS)
    url: str = Field(max_length=URL_MAX_CHARS)  # citable
    snippet: str = Field(max_length=SNIPPET_MAX_CHARS)


class SearchBackend(Protocol):
    """Whatever search service you plug in, behind one method. Tests use a fake."""

    def search(self, query: str, max_results: int, timeout_s: float) -> list[SearchResult]: ...


SEARCH_WEB = (
    "Search the public web for opinions, news or facts that Kestrel's exports don't hold. "
    "Returns titles, URLs and short snippets, not whole pages. "
    "Don't use it for counts or dates the exports contain: use count_rows for those."
)


def search_web(
    args: SearchWebArgs, backend: SearchBackend, timeout_s: Callable[[], float]
) -> list[dict]:
    """timeout_s() gives this call's limit: SEARCH_TIMEOUT_S or the run's time left, if less."""
    raise NotImplementedError("Chapter 15")


# --- read_file: one page of one export, to look at rows ---


class ReadFileArgs(StrictArgs):
    path: str = Field(description="A file name from the list above, e.g. shipments.csv")
    offset: int = Field(default=0, ge=0, description="Character offset; 0 for the first page")
    max_chars: int = Field(default=4_000, ge=200, le=READ_FILE_MAX_CHARS)


READ_FILE = (
    "Read one page of a CSV export, to look at example rows. Pages end on a whole line; "
    "the result header shows the character range, so the next page starts where it ends. "
    "Don't use it to count rows: one quarter of shipments is about a hundred pages. "
    "Use count_rows for every count. Files and their columns:\n"
)


def read_file(args: ReadFileArgs, root: Path) -> ProvenancedResult:
    raise NotImplementedError("Chapter 15")


# --- count_rows: counting in code, never in the model's head ---


class CountRowsArgs(StrictArgs):
    path: str = Field(description="A file name from the list above, e.g. shipments.csv")
    where: dict[str, str] = Field(
        default_factory=dict, max_length=5, description="column -> exact value; all must match"
    )
    date_column: str | None = Field(default=None, description="Column holding an ISO date")
    date_from: date | None = Field(default=None, description="Inclusive, YYYY-MM-DD")
    date_to: date | None = Field(default=None, description="Exclusive, YYYY-MM-DD")
    group_by: str | None = Field(default=None, description="Column to count per value of")

    @model_validator(mode="after")
    def dates_need_a_column(self) -> "CountRowsArgs":
        if (self.date_from or self.date_to) and not self.date_column:
            raise ValueError("date_from and date_to need date_column")
        return self


class CountRowsResult(BaseModel):
    path: str  # citable
    rows_in_file: int
    rows_in_period: int  # rows inside the date range, before `where` is applied
    rows_matched: int
    by_group: dict[str, int]  # empty without group_by


COUNT_ROWS = (
    "Count the rows of one CSV export that match every `where` value exactly, optionally "
    "inside a date range on one column (a row with an empty date cell is never inside) and "
    "grouped by a column. Use it for every count in your answer. Files and their columns:\n"
)


def count_rows(args: CountRowsArgs, root: Path) -> CountRowsResult:
    raise NotImplementedError("Chapter 15")


# --- calculate: arithmetic on numbers the model supplies ---


class CalculateArgs(StrictArgs):
    expression: str = Field(
        min_length=1, max_length=MAX_EXPRESSION_CHARS, description="e.g. (120 - 80) / 80 * 100"
    )


class CalculateResult(BaseModel):
    expression: str
    value: str  # a Decimal as text, so JSON never turns it into a float


CALCULATE = (
    "Evaluate arithmetic: numbers, + - * /, unary minus and parentheses. Use it for every "
    "total, difference, rate or percentage in your answer. It can't read files."
)


def calculate(args: CalculateArgs) -> CalculateResult:
    raise NotImplementedError("Chapter 15")


# --- The registry the loop will use ---


def describe_exports(root: Path) -> str:
    """One line per export: its name and header row, read from the folder at startup.

    Startup reads go through the sandbox too, so a symlink out of the folder is skipped.
    """
    lines = []
    for path in sorted(root.glob("*.csv")):
        try:
            resolved = resolve_in_sandbox(root, path.name)
        except SandboxError:
            continue
        with resolved.open(encoding="utf-8", errors="replace") as f:
            header = f.readline(HEADER_MAX_CHARS).strip()
        lines.append(f"- {path.name}: {header}")
    return "\n".join(lines)


def build_registry(
    root: Path,
    backend: SearchBackend,
    search_timeout_s: Callable[[], float],  # the loop supplies min(setting, time left)
    max_result_chars: int,
) -> ToolRegistry:
    root = root.resolve()  # once, at startup: the sandbox compares against this
    files = describe_exports(root)
    registry = ToolRegistry(max_result_chars)
    registry.register(
        Tool(
            "search_web",
            SEARCH_WEB,
            SearchWebArgs,
            partial(search_web, backend=backend, timeout_s=search_timeout_s),
        )
    )
    registry.register(
        Tool("read_file", READ_FILE + files, ReadFileArgs, partial(read_file, root=root))
    )
    registry.register(
        Tool("count_rows", COUNT_ROWS + files, CountRowsArgs, partial(count_rows, root=root))
    )
    registry.register(Tool("calculate", CALCULATE, CalculateArgs, calculate))
    return registry
