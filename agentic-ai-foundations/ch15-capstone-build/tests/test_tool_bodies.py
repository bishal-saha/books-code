"""The four tool bodies, run on the seeded exports and on small files written by the tests."""

from datetime import date
from pathlib import Path

import httpx
import pytest
from ch15.citations import citable_locations
from ch15.golden import load_golden_tasks, resolve_count
from ch15.model_client import ToolCall
from ch15.registry import ToolError
from ch15.tools import (
    CalculateArgs,
    CountRowsArgs,
    FixtureSearchBackend,
    HttpSearchBackend,
    ReadFileArgs,
    SearchWebArgs,
    UnconfiguredSearch,
    build_registry,
    calculate,
    count_rows,
    read_file,
    search_web,
)
from pydantic import SecretStr

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "search" / "carriers.json"


# --- read_file ---


def test_read_file_pages_end_on_a_whole_line(exports: Path) -> None:
    page = read_file(ReadFileArgs(path="shipments.csv", max_chars=1_000), exports)
    assert page.origin == "shipments.csv" and page.kind == "file"
    assert page.content.endswith("\n") and page.truncated
    start, end = page.shown[0]
    assert start == 0 and end == len(page.content) <= 1_000
    following = read_file(ReadFileArgs(path="shipments.csv", offset=end), exports)
    assert following.shown[0][0] == end  # the next page starts where this one ended


def test_read_file_offset_past_the_end(exports: Path) -> None:
    with pytest.raises(ToolError, match="past the end"):
        read_file(ReadFileArgs(path="products.csv", offset=10_000_000), exports)


def test_read_file_refuses_a_non_utf8_file(tmp_path: Path) -> None:
    (tmp_path / "blob.csv").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ToolError, match="not UTF-8"):
        read_file(ReadFileArgs(path="blob.csv"), tmp_path.resolve())


# --- count_rows ---


@pytest.mark.parametrize("task", [t for t in load_golden_tasks() if t.count_facts], ids=str)
def test_count_rows_agrees_with_the_golden_counts(task, exports: Path) -> None:
    """The agent's tool and the test's own csv count give the same numbers."""
    fact = task.count_facts[0]
    args = CountRowsArgs(path=fact.file, **fact.model_dump(exclude={"file", "top"}))
    result = count_rows(args, exports)
    expected = resolve_count(fact, exports)
    if fact.group_by:
        assert list(result.by_group.items())[: len(expected)] == expected
    else:
        assert result.rows_matched == expected[0][1]
    assert result.rows_in_period > 0  # every answered task's period is covered


def test_a_period_with_no_rows_is_visible(exports: Path) -> None:
    args = CountRowsArgs(
        path="shipments.csv",
        where={"late": "yes"},
        date_column="shipped_at",
        date_from=date(2026, 4, 1),
        date_to=date(2026, 7, 1),
    )
    result = count_rows(args, exports)
    assert (result.rows_in_file, result.rows_in_period, result.rows_matched) == (18_000, 0, 0)


def test_count_rows_names_unknown_columns_and_bad_dates(tmp_path: Path) -> None:
    (tmp_path / "s.csv").write_text("id,carrier,shipped_at\n1,A,2025-10-02\n2,B,soon\n")
    root = tmp_path.resolve()
    with pytest.raises(ToolError, match="no column late"):
        count_rows(CountRowsArgs(path="s.csv", where={"late": "yes"}), root)
    with pytest.raises(ToolError, match="line 3: 'soon' is not an ISO date"):
        count_rows(CountRowsArgs(path="s.csv", date_column="shipped_at"), root)


# --- calculate ---


@pytest.mark.parametrize(
    ("expression", "value"),
    [
        ("(139 - 93) / 93 * 100", "49.46236559139784946236559140"),
        ("10 * -2", "-20"),
        ("0.1 + 0.2", "0.3"),
        ("-(2 + 3) * 4", "-20"),
    ],
)
def test_calculate(expression: str, value: str) -> None:
    assert calculate(CalculateArgs(expression=expression)).value == value


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("1 / 0", "Division by zero"),
        ("2 ** 8", "Unexpected"),
        ("__import__('os')", "Unsupported"),
        ("(1 + 2", "ends too early"),
        ("1 2", "after a complete expression"),
        ("1e9", "Unsupported"),
    ],
)
def test_calculate_rejects(expression: str, message: str) -> None:
    with pytest.raises(ToolError, match=message):
        calculate(CalculateArgs(expression=expression))


# --- search_web and its backends ---


def test_fixture_backend_answers_by_subject() -> None:
    backend = FixtureSearchBackend(FIXTURE)
    hits = search_web(SearchWebArgs(query="harbour express reviews"), backend, lambda: 10.0)
    assert [h["url"] for h in hits] == [
        "https://reviews.example.com/harbour-express",
        "https://news.example.com/2025/11/harbour-express-weekend",
    ]
    assert search_web(SearchWebArgs(query="Northline Freight"), backend, lambda: 10.0) == []


def http_backend(handler) -> HttpSearchBackend:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpSearchBackend("https://search.example.com/v1", SecretStr("k"), client)


def test_http_backend_sends_the_key_in_a_header_and_drops_long_urls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "k" and "k" not in str(request.url)
        assert request.url.params["q"] == "Harbour Express"
        results = [
            {"title": "T" * 500, "url": "https://example.com/a", "snippet": "s"},
            {"title": "long", "url": "https://example.com/" + "x" * 600, "snippet": "s"},
        ]
        return httpx.Response(200, json={"results": results})

    hits = http_backend(handler).search("Harbour Express", 5, 3.0)
    assert [h.url for h in hits] == ["https://example.com/a"]
    assert len(hits[0].title) == 200


def registry_with(backend, exports: Path):
    return build_registry(exports, backend, lambda: 3.0, 16_000, citable_locations)


def test_search_failures_come_back_as_error_results(exports: Path) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("stalled", request=request)

    call = ToolCall(id="c1", name="search_web", arguments={"query": "Harbour Express"})
    for backend, text in [
        (http_backend(timeout), "timed out"),
        (http_backend(lambda r: httpx.Response(500)), "HTTP 500"),
        (UnconfiguredSearch(), "not configured"),
    ]:
        registry = registry_with(backend, exports)
        result = registry.dispatch(call)
        assert result.is_error and text in result.content
        assert registry.citable == set()  # an error result makes nothing citable


def test_successful_results_fill_the_citable_set(exports: Path) -> None:
    registry = registry_with(FixtureSearchBackend(FIXTURE), exports)
    calls = [
        ToolCall(id="1", name="search_web", arguments={"query": "Swiftway Parcel"}),
        ToolCall(id="2", name="count_rows", arguments={"path": "shipments.csv"}),
        ToolCall(id="3", name="read_file", arguments={"path": "../kestrel.sqlite"}),
        ToolCall(id="4", name="calculate", arguments={"expression": "1 + 1"}),
    ]
    results = [registry.dispatch(c) for c in calls]
    assert [r.is_error for r in results] == [False, False, True, False]
    assert registry.citable == {"https://reviews.example.com/swiftway-parcel", "shipments.csv"}
