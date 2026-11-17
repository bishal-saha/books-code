"""Chapter 13 test setup.

Puts this folder on sys.path so `import ch13` works when pytest runs from the book folder,
and provides `kestrel_url` (the server you started with `uv run kestrel up` if it answers,
otherwise the same seeded API started inside the test process) and `registry`, the operations
agent's tools against that API.
"""

import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ch13.kestrel_tools import build_ops_registry  # noqa: E402
from ch13.settings import DEFAULT_KESTREL_URL  # noqa: E402
from ch13.tools import ToolRegistry  # noqa: E402


@pytest.fixture(scope="session")
def kestrel_url() -> Iterator[str]:
    try:
        httpx.get(f"{DEFAULT_KESTREL_URL}/health", timeout=1.0).raise_for_status()
    except httpx.HTTPError:
        from kestrel.services import serve_in_thread

        server, url = serve_in_thread(scale=1.0)  # same seed and scale as `kestrel up`
        yield url
        server.shutdown()
    else:
        yield DEFAULT_KESTREL_URL


@pytest.fixture
def registry(kestrel_url: str) -> Iterator[ToolRegistry]:
    with httpx.Client(base_url=kestrel_url, timeout=10.0) as http:
        yield build_ops_registry(http)
