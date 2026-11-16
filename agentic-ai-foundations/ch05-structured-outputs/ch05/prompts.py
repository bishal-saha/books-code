"""Versioned prompt files, loaded as in Chapter 4, with the generated schema filled in."""

import json
from pathlib import Path
from string import Template

from pydantic import BaseModel

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Prompt(BaseModel):
    name: str
    version: int
    change: str
    body: str


def load_prompt(name: str, version: int) -> Prompt:
    """Chapter 4's loader: a front-matter header (name, version, change), then the body."""
    text = (PROMPTS_DIR / f"{name}_v{version}.md").read_text(encoding="utf-8")
    _, header, body = text.split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    prompt = Prompt(**fields, body=body.strip())
    if prompt.version != version:
        raise ValueError(f"{name}_v{version}.md declares version {prompt.version}")
    return prompt


def system_prompt(prompt: Prompt, output_model: type[BaseModel]) -> str:
    """Put the output model's JSON Schema where the prompt says $schema."""
    schema = json.dumps(output_model.model_json_schema(), indent=2)
    return Template(prompt.body).substitute(schema=schema)


def render_claim(text: str) -> str:
    # As in Chapter 4: data goes inside <data>, with < and > replaced so it can't close the tag.
    return "<data>\n" + text.replace("<", "&lt;").replace(">", "&gt;") + "\n</data>"
