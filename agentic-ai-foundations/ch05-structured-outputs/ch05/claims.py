"""Expense claims: the fixture texts and one extraction call per claim."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from ch05.extract import Extraction, extract
from ch05.model_client import ModelClient
from ch05.models import ExpenseClaim
from ch05.prompts import load_prompt, render_claim, system_prompt

CLAIMS_FILE = Path(__file__).parent / "claims.jsonl"
PROMPT_VERSION = 1


def load_claims(path: Path = CLAIMS_FILE) -> Iterator[tuple[str, str]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            yield record["claim_id"], record["text"]


def extract_claim(
    client: ModelClient, text: str, *, max_attempts: int, max_tokens: int, today: date
) -> Extraction[ExpenseClaim]:
    system = system_prompt(load_prompt("extract_claim", PROMPT_VERSION), ExpenseClaim)
    return extract(
        client, system, render_claim(text), ExpenseClaim,
        max_attempts=max_attempts, max_tokens=max_tokens, context={"today": today},
    )  # fmt: skip
