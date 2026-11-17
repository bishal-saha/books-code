"""The file sandbox: every path in the chapter's table must be refused, and real files allowed."""

import os
from pathlib import Path

import pytest
from ch14.registry import ToolError
from ch14.sandbox import SandboxError, resolve_in_sandbox, sandbox_name


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A copy of the chapter's layout: .kestrel/ with the database next to exports/."""
    kestrel = tmp_path / ".kestrel"
    (kestrel / "exports").mkdir(parents=True)
    (kestrel / "exports-old").mkdir()
    (kestrel / "kestrel.sqlite").write_text("not a csv")
    (kestrel / "exports-old" / "shipments.csv").write_text("old")
    (kestrel / "exports" / "shipments.csv").write_text("shipment_id,carrier\n")
    os.symlink(kestrel / "kestrel.sqlite", kestrel / "exports" / "latest.csv")
    return (kestrel / "exports").resolve()


@pytest.mark.parametrize(
    "requested",
    [
        "../kestrel.sqlite",  # '..' climbs out of the root
        "/etc/passwd",  # absolute paths ignore the root
        "../exports-old/shipments.csv",  # a sibling whose name starts with the root's name
        "latest.csv",  # inside by name, a symlink to a file outside
        "missing.csv",  # inside, but no such file
        ".",  # the root itself is not a file
        "",  # nor is the empty path
        "ship\x00ments.csv",  # a NUL byte: an error from resolve(), turned into a refusal
    ],
)
def test_refused(root: Path, requested: str) -> None:
    with pytest.raises(SandboxError):
        resolve_in_sandbox(root, requested)


def test_allowed_and_named_once(root: Path) -> None:
    for requested in ("shipments.csv", "./shipments.csv", "sub/../shipments.csv"):
        resolved = resolve_in_sandbox(root, requested)
        assert sandbox_name(root, resolved) == "shipments.csv"


def test_sandbox_error_is_a_tool_error(root: Path) -> None:
    """So the registry returns it as a result with is_error=True (Chapter 6), not a crash."""
    with pytest.raises(ToolError, match="Files in the sandbox: latest.csv, shipments.csv"):
        resolve_in_sandbox(root, "returns.csv")


def test_unresolved_root_is_a_programming_error(root: Path) -> None:
    with pytest.raises(ValueError):
        resolve_in_sandbox(Path("relative/exports"), "shipments.csv")


def test_the_naive_checks_fail(root: Path) -> None:
    """Why the rule resolves first: the chapter's three naive checks, each fooled once."""
    joined = os.path.join(str(root), "/etc/passwd")
    assert joined == "/etc/passwd"  # join throws the base away
    sibling = str(root.parent / "exports-old" / "shipments.csv")
    assert sibling.startswith(str(root))  # string prefix accepts the sibling
    normalised = os.path.normpath(os.path.join(str(root), "latest.csv"))
    assert normalised.startswith(str(root) + os.sep)  # text normalising ignores the symlink
    assert not Path(normalised).resolve().is_relative_to(root)
