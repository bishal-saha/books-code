"""Chapter 4's loader for versioned prompt files: a front-matter header, then the body."""

from pathlib import Path

from pydantic import BaseModel

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
