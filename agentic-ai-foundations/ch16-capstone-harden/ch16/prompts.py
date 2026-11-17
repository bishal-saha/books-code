"""Chapter 4's loader for versioned prompt files, plus the research assistant's system prompt.

load_prompt is copied unchanged from Chapter 13. New in Chapter 14: build_system_prompt fills
the two placeholders: the run's date and the JSON Schema generated from FinalAnswer.
"""

import json
from datetime import date
from html import escape
from pathlib import Path
from string import Template

from pydantic import BaseModel

from ch16.answer import FinalAnswer

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Prompt(BaseModel):
    name: str
    version: int
    change: str
    body: str


def load_prompt(name: str, version: int) -> Prompt:
    text = (PROMPTS_DIR / f"{name}_v{version}.md").read_text(encoding="utf-8")
    _, header, body = text.split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    prompt = Prompt(**fields, body=body.strip())
    if prompt.version != version:
        raise ValueError(f"{name}_v{version}.md declares version {prompt.version}")
    return prompt


def build_system_prompt(today: date, version: int = 1) -> str:
    """The schema comes from the same class that validates the reply, so they can't drift."""
    body = load_prompt("research_assistant", version).body
    schema = json.dumps(FinalAnswer.model_json_schema(), indent=1)
    return Template(body).substitute(today=escape(today.isoformat()), answer_schema=schema)
