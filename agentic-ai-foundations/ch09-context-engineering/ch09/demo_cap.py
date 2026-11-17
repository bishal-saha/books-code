"""read_doc with a deliberately tiny cap, then the page the marker points to.

uv run python -m ch09.demo_cap      # needs `uv run kestrel up` (or --no-serve) once, for docs
"""

from ch09.doc_tools import DOCS_ROOT, build_doc_registry
from ch09.model_client import ToolCall


def main() -> None:
    registry = build_doc_registry(DOCS_ROOT, max_result_chars=300)  # tiny, to force a cut
    first = registry.dispatch(
        ToolCall(id="c1", name="read_doc", arguments={"path": "shipping-policy.md"})
    )
    print(first.content)
    page = registry.dispatch(
        ToolCall(id="c2", name="read_doc", arguments={"path": "shipping-policy.md", "offset": 165})
    )
    print(page.content.splitlines()[0])  # the header of the next page
    print("3 working days" in page.content)


if __name__ == "__main__":
    main()
