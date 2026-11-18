"""The tool contracts: names, schemas, descriptions and caps, checked before any body exists."""

import json
import re
from pathlib import Path

import pytest
from ch14.design_check import max_search_chars
from ch14.model_client import ToolCall
from ch14.settings import Settings
from ch14.tools import (
    SEARCH_MAX_RESULTS,
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
    # No golden task's expected value appears in a definition the model sees (139 and 93)
    definitions = json.dumps([d.model_dump() for d in registry.definitions()])
    assert not re.search(r"\b(139|93)\b", definitions)


def test_file_tools_list_the_exports_and_their_columns(registry) -> None:
    by_name = {d.name: d for d in registry.definitions()}
    for name in ("read_file", "count_rows"):
        assert "- shipments.csv: shipment_id,order_id,carrier" in by_name[name].description


def test_search_results_fit_under_the_result_cap() -> None:
    """Oversized JSON becomes an error (Chapter 9), which would leave the model no URLs."""
    assert max_search_chars(SEARCH_MAX_RESULTS) <= Settings().tool_result_max_chars


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
