"""Two read-only tools over Kestrel's internal docs: list_docs and read_doc."""

from functools import partial
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ch09.registry import Tool, ToolError, ToolRegistry
from ch09.truncate import ProvenancedResult, cap_result

DOCS_ROOT = Path(".kestrel/docs")  # written by `uv run kestrel up` in this folder

LIST_DOCS_DESCRIPTION = (
    "List every internal Kestrel document (handbook pages and policies). Returns the path, "
    "title and length in characters of each. Call this first: read_doc only accepts paths "
    "that appear in this list."
)
READ_DOC_DESCRIPTION = (
    "Read one internal document by a path returned by list_docs. Long documents are "
    "truncated: the header shows which character ranges you are seeing, and a marker names "
    "the omitted range. Pass offset to read from that position."
)


class ListDocsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadDocInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(max_length=200, description="A path exactly as list_docs returned it.")
    offset: int = Field(0, ge=0, description="Character position to start reading from.")


def doc_paths(root: Path) -> set[str]:
    """Docs-relative paths: the only form list_docs returns and read_doc accepts."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*.md") if p.name != "README.md"}


def list_docs(root: Path, args: ListDocsInput) -> list[dict[str, object]]:
    docs = []
    for path in sorted(doc_paths(root)):
        text = (root / path).read_text(encoding="utf-8")
        title = text.splitlines()[0].removeprefix("# ") if text else path
        docs.append({"path": path, "title": title, "chars": len(text)})
    return docs


def read_doc(root: Path, max_chars: int, args: ReadDocInput) -> ProvenancedResult:
    if args.path not in doc_paths(root):  # also keeps reads inside the docs folder
        raise ToolError(f"Unknown doc path {args.path!r}. Call list_docs and use a path from it.")
    text = (root / args.path).read_text(encoding="utf-8")
    try:
        return cap_result(
            text, origin=args.path, kind="file", max_chars=max_chars, offset=args.offset
        )
    except ValueError as exc:  # an offset past the end: tell the model the length
        raise ToolError(str(exc)) from exc


def build_doc_registry(root: Path, max_result_chars: int) -> ToolRegistry:
    registry = ToolRegistry(max_result_chars)
    registry.register(Tool("list_docs", LIST_DOCS_DESCRIPTION, ListDocsInput,
                           partial(list_docs, root)))  # fmt: skip
    registry.register(Tool("read_doc", READ_DOC_DESCRIPTION, ReadDocInput,
                           partial(read_doc, root, max_result_chars)))  # fmt: skip
    return registry
