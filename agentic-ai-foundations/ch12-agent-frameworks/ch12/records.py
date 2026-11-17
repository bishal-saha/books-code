"""Checks that every decision record answers the checklist's questions, then lists them.

uv run python -m ch12.records
"""

from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent
DECISIONS = FOLDER / "decisions"
REQUIRED = ("Decision", "Placement", "Need", "Gates", "Revisit if")


def fields(text: str) -> dict[str, str]:
    """'Key: value' lines, with indented or plain continuation lines joined to the value."""
    out: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        head, sep, rest = line.partition(": ")
        if sep and head and not head.startswith((" ", "-", "#")) and len(head) < 30:
            key = head.strip()
            out[key] = rest.strip()
        elif key and line.strip() and not line.startswith("#"):
            out[key] += " " + line.strip()
    return out


def problems(path: Path) -> list[str]:
    found = fields(path.read_text(encoding="utf-8"))
    return [f"{path.name}: missing '{name}:'" for name in REQUIRED if not found.get(name)]


def main() -> None:
    paths = sorted(DECISIONS.glob("*.md"))
    issues = [p for path in paths for p in problems(path)]
    for path in paths:
        decision = fields(path.read_text(encoding="utf-8"))["Decision"]
        print(f"{path.stem:<24} {decision}")
    print(f"{len(paths)} records, {len(issues)} problems")
    for issue in issues:
        print(" ", issue)


if __name__ == "__main__":
    main()
