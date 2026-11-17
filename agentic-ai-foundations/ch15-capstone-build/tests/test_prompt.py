"""The system prompt keeps Chapter 4's six sections and carries the generated schema."""

import re
from datetime import date

from ch15.prompts import build_system_prompt

SECTIONS = ["Role", "Task", "Constraints", "Data", "Output format", "When you don't know"]


def test_six_sections_in_order() -> None:
    prompt = build_system_prompt(date(2026, 1, 15))
    assert re.findall(r"^## (.+)$", prompt, flags=re.M) == SECTIONS


def test_date_and_schema_are_filled() -> None:
    prompt = build_system_prompt(date(2026, 1, 15))
    assert "<data>\nToday's date: 2026-01-15\n</data>" in prompt
    assert '"needs_info"' in prompt and "$today" not in prompt and "$answer_schema" not in prompt
    assert "NEEDS INFO:" in prompt
