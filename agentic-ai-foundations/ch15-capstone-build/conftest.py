"""Chapter 15 test setup (copied from Chapter 14).

Puts this folder on sys.path so `import ch15` works when pytest runs from the book folder, and
provides `exports`: the seeded CSV exports (same seed as `uv run kestrel up`), written once
per session into a temporary folder, so the tests never depend on your .kestrel/.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session")
def exports(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from kestrel.data import generate
    from kestrel.workspace import write_exports

    folder = tmp_path_factory.mktemp("kestrel") / "exports"
    write_exports(generate(2026, 1.0), folder)
    return folder.resolve()
