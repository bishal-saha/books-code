"""The research assistant's four read-only tools: Chapter 14's contracts, Chapter 15's bodies.

Each tool follows Chapter 8: a verb-first name, a description that says when (and when not)
to use it, a strict pydantic input model that generates the JSON Schema, a fixed output
shape, and errors written for the model. Every function takes its validated arguments only;
build_registry binds the rest (sandbox root, search backend, timeout) with functools.partial.
New in Chapter 15: the four bodies, HttpSearchBackend (illustrative: the book picks no search
service), FixtureSearchBackend (hand-written results for tests and demos), UnconfiguredSearch,
and build_registry's citable_from argument.
"""

import csv
import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation
from functools import partial
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from ch15.registry import CitableFrom, Tool, ToolError, ToolRegistry
from ch15.sandbox import SandboxError, resolve_in_sandbox, sandbox_name
from ch15.truncate import ProvenancedResult

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
    """Whatever search service Chapter 15 picks, behind one method. Tests use a fake."""

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
    results = backend.search(args.query, args.max_results, timeout_s())
    return [r.model_dump() for r in results[: args.max_results]]


def fit_result(item: dict) -> SearchResult | None:
    """Cap title and snippet. Drop a result whose URL is too long: a cut URL can't be cited."""
    url = str(item.get("url", ""))
    if not url.startswith(("https://", "http://")) or len(url) > URL_MAX_CHARS:
        return None
    return SearchResult(
        title=str(item.get("title", ""))[:TITLE_MAX_CHARS],
        url=url,
        snippet=str(item.get("snippet", ""))[:SNIPPET_MAX_CHARS],
    )


class HttpSearchBackend:
    """Illustrative: a JSON search API reached with httpx. The book picks no search service, so
    this speaks a small contract of its own: GET <endpoint>?q=...&count=N with the key in an
    X-API-Key header, answering {"results": [{"title", "url", "snippet"}, ...]}. Adapt the
    request and the parsing to your service's documented API."""

    def __init__(self, endpoint: str, api_key: SecretStr, client: httpx.Client | None = None):
        self._endpoint = endpoint
        self._headers = {"X-API-Key": api_key.get_secret_value()}  # a header, never the URL
        self._client = client or httpx.Client()

    def search(self, query: str, max_results: int, timeout_s: float) -> list[SearchResult]:
        response = self._client.get(
            self._endpoint,
            params={"q": query, "count": max_results},
            headers=self._headers,
            timeout=timeout_s,  # per request: SEARCH_TIMEOUT_S or the run's time left, if less
        )  # httpx.TimeoutException propagates: the registry turns it into a "timed out" result
        if response.status_code != 200:
            raise ToolError(f"The search service answered HTTP {response.status_code}.")
        try:
            items = response.json()["results"]
        except (ValueError, KeyError, TypeError):
            raise ToolError("The search service returned a response without results.") from None
        fitted = (fit_result(i) for i in items if isinstance(i, dict))
        return [r for r in fitted if r is not None][:max_results]


class FixtureSearchBackend:
    """Hand-written search results (not a recording) for tests and the demo: a query gets the
    results of every subject it names. Anything else gets no results, as a live search might."""

    def __init__(self, fixture: Path) -> None:
        data = json.loads(fixture.read_text(encoding="utf-8"))
        self._results = {k: [SearchResult(**r) for r in v] for k, v in data["results"].items()}
        self.queries: list[str] = []

    def search(self, query: str, max_results: int, timeout_s: float) -> list[SearchResult]:
        self.queries.append(query)
        hits = [r for k, rs in self._results.items() if k.lower() in query.lower() for r in rs]
        return hits[:max_results]


class UnconfiguredSearch:
    """Used when SEARCH_ENDPOINT is empty: the tool stays in the set and says why it can't run."""

    def search(self, query: str, max_results: int, timeout_s: float) -> list[SearchResult]:
        raise ToolError(
            "search_web is not configured on this machine. Answer from the exports and list "
            "what needed the web under `missing`."
        )


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


def read_text(root: Path, requested: str) -> tuple[str, str]:
    """(sandbox name, text) of one export, through the sandbox."""
    resolved = resolve_in_sandbox(root, requested)  # raises SandboxError, a ToolError
    try:
        return sandbox_name(root, resolved), resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ToolError(f"{requested!r} is not UTF-8 text. Read one of the CSV exports.") from None


def read_file(args: ReadFileArgs, root: Path) -> ProvenancedResult:
    name, text = read_text(root, args.path)
    if args.offset >= len(text):
        raise ToolError(f"offset {args.offset} is past the end of {name} ({len(text)} chars).")
    end = min(args.offset + args.max_chars, len(text))
    if end < len(text):  # end the page on a whole line, unless one line fills the page
        last_newline = text.rfind("\n", args.offset, end)
        end = last_newline + 1 if last_newline >= args.offset else end
    return ProvenancedResult(
        origin=name,  # the file's sandbox name: what citable_locations records
        kind="file",
        total_chars=len(text),
        shown=[(args.offset, end)],
        truncated=args.offset > 0 or end < len(text),
        content=text[args.offset : end],
    )


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
    name, text = read_text(root, args.path)
    reader = csv.DictReader(text.splitlines())
    columns = set(reader.fieldnames or ())
    asked = [*args.where, args.date_column, args.group_by]
    if unknown := sorted({c for c in asked if c} - columns):
        raise ToolError(
            f"{name} has no column {', '.join(unknown)}. Columns: {', '.join(reader.fieldnames)}."
        )
    in_file = in_period = matched = 0
    groups: Counter[str] = Counter()
    for line, row in enumerate(reader, start=2):  # line 1 is the header
        in_file += 1
        if args.date_column:
            cell = row[args.date_column]
            if not cell:
                continue  # an empty date cell is never inside a range
            try:
                day = date.fromisoformat(cell[:10])
            except ValueError:
                raise ToolError(f"{name} line {line}: {cell!r} is not an ISO date.") from None
            if (args.date_from and day < args.date_from) or (args.date_to and day >= args.date_to):
                continue
        in_period += 1
        if all(row[col] == value for col, value in args.where.items()):
            matched += 1
            if args.group_by:
                groups[row[args.group_by]] += 1
    return CountRowsResult(
        path=name,
        rows_in_file=in_file,
        rows_in_period=in_period,
        rows_matched=matched,
        by_group=dict(sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))),
    )


# --- calculate: arithmetic on numbers the model supplies ---


class CalculateArgs(StrictArgs):
    expression: str = Field(
        min_length=1, max_length=MAX_EXPRESSION_CHARS, description="e.g. (139 - 93) / 93 * 100"
    )


class CalculateResult(BaseModel):
    expression: str
    value: str  # a Decimal as text, so JSON never turns it into a float


CALCULATE = (
    "Evaluate arithmetic: numbers, + - * /, unary minus and parentheses. Use it for every "
    "total, difference, rate or percentage in your answer. It can't read files."
)


_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|(.))")


def tokenize(expression: str) -> list[str]:
    tokens = []
    for number, symbol in _TOKEN.findall(expression.strip()):
        if symbol and symbol not in "+-*/()":
            raise ToolError(f"Unsupported character {symbol!r}. Use numbers, + - * / and ( ).")
        tokens.append(number or symbol)
    return tokens


class _Parser:
    """Recursive descent, one method per grammar rule:
    sum := term (('+' | '-') term)*   term := factor (('*' | '/') factor)*
    factor := ('+' | '-') factor | number | '(' sum ')'"""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens, self.i = tokens, 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise ToolError("The expression ends too early.")
        self.i += 1
        return token

    def sum(self) -> Decimal:
        value = self.term()
        while self.peek() in ("+", "-"):
            value = value + self.term() if self.take() == "+" else value - self.term()
        return value

    def term(self) -> Decimal:
        value = self.factor()
        while self.peek() in ("*", "/"):
            value = value * self.factor() if self.take() == "*" else value / self.factor()
        return value

    def factor(self) -> Decimal:
        token = self.take()
        if token in ("+", "-"):
            value = self.factor()
            return value if token == "+" else -value
        if token == "(":
            value = self.sum()
            if self.take() != ")":
                raise ToolError("A '(' has no matching ')'.")
            return value
        if token[0].isdigit():
            return Decimal(token)
        raise ToolError(f"Unexpected {token!r} in the expression.")


def calculate(args: CalculateArgs) -> CalculateResult:
    parser = _Parser(tokenize(args.expression))
    try:
        value = parser.sum()
    except (DivisionByZero, InvalidOperation):
        raise ToolError("Division by zero. Check the numbers you passed.") from None
    if parser.peek() is not None:
        raise ToolError(f"Unexpected {parser.peek()!r} after a complete expression.")
    return CalculateResult(expression=args.expression, value=str(value))


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
    citable_from: CitableFrom | None = None,  # new in Chapter 15: citable_locations
) -> ToolRegistry:
    root = root.resolve()  # once, at startup: the sandbox compares against this
    files = describe_exports(root)
    registry = ToolRegistry(max_result_chars, citable_from)
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
