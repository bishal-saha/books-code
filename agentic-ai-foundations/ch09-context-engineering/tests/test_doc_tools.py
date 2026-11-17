"""list_docs and read_doc over the docs `kestrel up` writes (copied into a temp folder)."""

from pathlib import Path

import pytest
from ch09.doc_tools import build_doc_registry
from ch09.model_client import ToolCall
from kestrel.workspace import copy_docs


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    copy_docs(tmp_path / "docs")
    return tmp_path / "docs"


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(id="call_1", name=name, arguments=arguments)


def test_list_docs_shows_titles_that_mark_the_retired_page(docs):
    result = build_doc_registry(docs, 4_000).dispatch(call("list_docs"))
    assert not result.is_error
    assert '"path": "shipping-policy-v2-OUTDATED.md"' in result.content
    assert "Shipping policy (v2, superseded on 1 March 2025)" in result.content
    assert "README.md" not in result.content


def test_read_doc_returns_the_file_with_its_path_as_origin(docs):
    result = build_doc_registry(docs, 4_000).dispatch(call("read_doc", path="shipping-policy.md"))
    header, body = result.content.split("\n", 1)
    assert header.startswith("[origin: shipping-policy.md | kind: file | shown: 0-")
    assert "3 working days" in body and not result.is_error


def test_a_long_doc_is_truncated_and_paged(docs):
    registry = build_doc_registry(docs, 300)
    first = registry.dispatch(call("read_doc", path="shipping-policy.md"))
    assert "| truncated]" in first.content.splitlines()[0]
    second = registry.dispatch(call("read_doc", path="shipping-policy.md", offset=200))
    assert "shown: 200-500 of" in second.content


@pytest.mark.parametrize("path", ["nope.md", "../.env", "/etc/passwd"])
def test_unknown_or_escaping_paths_are_error_results(docs, path):
    result = build_doc_registry(docs, 4_000).dispatch(call("read_doc", path=path))
    assert result.is_error and "Call list_docs" in result.content


def test_an_offset_past_the_end_tells_the_model_the_length(docs):
    result = build_doc_registry(docs, 4_000).dispatch(
        call("read_doc", path="returns-policy.md", offset=99_999)
    )
    assert result.is_error and "past the end" in result.content
