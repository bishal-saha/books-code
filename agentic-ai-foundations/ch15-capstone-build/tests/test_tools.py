"""The tool contracts (copied from Chapter 14) and, new in Chapter 15, the tool bodies."""

import json
import re
from pathlib import Path

import pytest
from ch15.model_client import ToolCall
from ch15.settings import Settings
from ch15.tools import (
    SEARCH_MAX_RESULTS,
    SNIPPET_MAX_CHARS,
    TITLE_MAX_CHARS,
    URL_MAX_CHARS,
    CountRowsArgs,
    SearchResult,
    build_registry,
    describe_exports,
)
from pydantic import ValidationError


class NoSearch:
    def search(self, query: str, max_results: int, timeout_s: float) -> list[SearchResult]:
        return []


@pytest.fixture
def registry(exports: Path):
    s = Settings()
    return build_registry(exports, NoSearch(), lambda: s.search_timeout_s, s.tool_result_max_chars)


def test_four_verb_first_tools(registry) -> None:
    names = [d.name for d in registry.definitions()]
    assert names == ["search_web", "read_file", "count_rows", "calculate"]
    for d in registry.definitions():
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", d.name)
        assert d.input_schema["type"] == "object"
        assert re.search(r"\b(Use it|Don't use it|can't)\b", d.description)  # when, and when not


def test_file_tools_list_the_exports_and_their_columns(registry) -> None:
    by_name = {d.name: d for d in registry.definitions()}
    for name in ("read_file", "count_rows"):
        assert "- shipments.csv: shipment_id,order_id,carrier" in by_name[name].description


def test_search_results_fit_under_the_result_cap() -> None:
    """Oversized JSON becomes an error (Chapter 9), which would leave the model no URLs."""
    worst = SearchResult(
        title="t" * TITLE_MAX_CHARS, url="u" * URL_MAX_CHARS, snippet="s" * SNIPPET_MAX_CHARS
    )
    page = json.dumps([worst.model_dump()] * SEARCH_MAX_RESULTS)
    assert len(page) <= Settings().tool_result_max_chars


def test_dates_need_a_column() -> None:
    with pytest.raises(ValidationError, match="need date_column"):
        CountRowsArgs(path="shipments.csv", date_from="2025-10-01")


def test_unknown_argument_comes_back_as_a_tool_result(registry) -> None:
    result = registry.dispatch(
        ToolCall(id="c1", name="count_rows", arguments={"path": "shipments.csv", "sql": "x"})
    )
    assert result.is_error and "sql" in result.content


def test_export_descriptions_skip_a_symlink_out_of_the_sandbox(tmp_path: Path) -> None:
    (tmp_path / "exports").mkdir()
    (tmp_path / "secret.csv").write_text("password\n")
    (tmp_path / "exports" / "shipments.csv").write_text("shipment_id,carrier\n")
    (tmp_path / "exports" / "latest.csv").symlink_to(tmp_path / "secret.csv")
    assert (
        describe_exports((tmp_path / "exports").resolve()) == "- shipments.csv: shipment_id,carrier"
    )
