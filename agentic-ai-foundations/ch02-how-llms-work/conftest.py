"""Chapter 2 test setup.

Puts this folder on sys.path so `import ch02` works when pytest runs from the book folder.
Provides test settings, the seeded Kestrel docs, and `fake_client`: a stand-in for
`anthropic.Anthropic` that answers from canned responses and records every request.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from anthropic.types import Message, MessageTokensCount

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ch02.settings import Settings  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"


class FakeClient:
    """count_tokens reports `count`; create returns the canned responses in order."""

    def __init__(self, count: int, responses: list[Message]) -> None:
        self.requests: list[dict[str, Any]] = []
        self._count = count
        self._responses = iter(responses)
        self.messages = SimpleNamespace(count_tokens=self._count_tokens, create=self._create)

    def _count_tokens(self, **request: Any) -> MessageTokensCount:
        return MessageTokensCount(input_tokens=self._count)

    def _create(self, **request: Any) -> Message:
        self.requests.append(request)
        return next(self._responses)


@pytest.fixture
def fake_client():
    def make(count: int = 500, responses: str | None = None) -> FakeClient:
        raw = json.loads((FIXTURES / responses).read_text()) if responses else []
        return FakeClient(count, [Message.model_validate(r) for r in raw])

    return make


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    from kestrel.workspace import copy_docs  # the same copy `uv run kestrel up` makes

    copy_docs(tmp_path / "docs")
    return tmp_path / "docs"


def _settings(docs_dir: Path, key: str | None) -> Settings:
    return Settings(
        model="test-model",
        api_key=key,
        input_price_per_mtok=Decimal("1.25"),  # test prices, not any provider's
        output_price_per_mtok=Decimal("6.25"),
        context_window_tokens=10_000,  # a test window, not any model's
        docs_dir=docs_dir,
        model_timeout_s=5.0,
    )


@pytest.fixture
def settings(docs_dir: Path) -> Settings:
    return _settings(docs_dir, "test-key")


@pytest.fixture
def settings_without_key(docs_dir: Path) -> Settings:
    return _settings(docs_dir, None)
