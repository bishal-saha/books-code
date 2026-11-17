"""Every decision record answers the same questions; the checklist keeps its sections."""

from pathlib import Path

from ch12.records import DECISIONS, problems

CHECKLIST = Path(__file__).resolve().parent.parent / "checklist.md"


def test_every_record_has_the_required_fields():
    paths = sorted(DECISIONS.glob("*.md"))
    assert [p.stem for p in paths] == [
        "capstone",
        "expense-claims",
        "late-shipments",
        "return-authorisations",
    ]
    assert [issue for p in paths for issue in problems(p)] == []


def test_a_record_without_revisit_conditions_is_flagged(tmp_path):
    record = tmp_path / "x.md"
    record.write_text("Decision: build\nPlacement: agent\nNeed: none\nGates: met\n")
    assert problems(record) == ["x.md: missing 'Revisit if:'"]


def test_checklist_sections_in_order():
    headings = [line for line in CHECKLIST.read_text().splitlines() if line.startswith("## ")]
    assert [h.split(".")[0] for h in headings] == [f"## {n}" for n in range(8)]
