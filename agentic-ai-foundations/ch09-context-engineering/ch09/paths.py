"""A path check for the capstone's read-file tool. Chapter 14 turns it into the file sandbox."""

from pathlib import Path


def resolve_inside(folder: str | Path, relative: str) -> Path | None:
    """Return the resolved path if it stays inside folder, else None."""
    root = Path(folder).resolve()
    candidate = (root / relative).resolve()
    return candidate if candidate.is_relative_to(root) else None
