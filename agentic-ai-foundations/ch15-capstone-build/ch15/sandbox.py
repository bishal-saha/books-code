"""The file sandbox: one folder the file tools may read, enforced by a path check.

It is a path check, not process isolation: it limits which files read_file and count_rows
open, nothing else.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath

from ch15.registry import ToolError


class SandboxError(ToolError):
    """A path the sandbox refused. The registry returns it as a tool result with is_error=True."""


def resolve_in_sandbox(root: Path, requested: str) -> Path:
    """Return the real path of `requested` inside `root`, or raise SandboxError.

    `root` must already be resolved (once, at startup). The order matters: reject absolute
    input, resolve with symlinks followed, then compare the resolved path with the root.
    """
    if not root.is_absolute():
        raise ValueError("resolve the sandbox root once at startup: Path(...).resolve()")
    if PurePosixPath(requested).is_absolute() or PureWindowsPath(requested).is_absolute():
        raise SandboxError(
            f"Path rejected: {requested!r} is absolute. "
            "Use a path relative to the sandboxed folder, such as shipments.csv."
        )
    try:
        resolved = (root / requested).resolve()  # follows symlinks and collapses '..'
    except (OSError, ValueError) as exc:  # e.g. a NUL byte in the path
        raise SandboxError(f"Path rejected: {requested!r} is not a valid file name.") from exc
    if not resolved.is_relative_to(root):  # compares path parts, not string prefixes
        raise SandboxError(
            f"Path rejected: {requested!r} is outside the sandboxed folder. "
            "Use a path relative to it, such as shipments.csv."
        )
    if not resolved.is_file():
        names = ", ".join(sorted(p.name for p in root.glob("*.csv")))
        raise SandboxError(f"No such file: {requested!r}. Files in the sandbox: {names}.")
    return resolved


def sandbox_name(root: Path, resolved: Path) -> str:
    """The one name a file has in citations: its path relative to the root, with '/'."""
    return resolved.relative_to(root).as_posix()
