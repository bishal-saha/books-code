"""Chapter 4 test setup.

Puts this folder on sys.path so `import ch04` works when pytest runs from the book folder.
Provides `make_ticket` and `kestrel_url`: the server you started with `uv run kestrel up` if
it answers, otherwise the same seeded API started inside the test process.
"""

import sys
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ch04.prompt_builder import Ticket, TicketMessage  # noqa: E402
from ch04.settings import DEFAULT_KESTREL_URL  # noqa: E402


@pytest.fixture
def make_ticket() -> Callable[..., Ticket]:
    """Builds a test ticket. The values are made up, not rows from the mocks."""

    def _make(body: str = "The Fernhill folding chair arrived with a bent leg.") -> Ticket:
        return Ticket(
            ticket_id="T-999999",
            order_id=None,
            channel="email",
            subject="Chair arrived damaged",
            messages=[TicketMessage(author="customer", sent_at=datetime(2025, 10, 22), body=body)],
        )

    return _make


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
