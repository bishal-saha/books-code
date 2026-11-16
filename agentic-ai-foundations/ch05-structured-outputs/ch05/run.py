"""Extract every fixture claim, check it against the expense policy, print Priya's queue.

uv run python -m ch05.run --demo                    # scripted fake model, no key
uv run --env-file .env python -m ch05.run           # real model, prompt-only JSON
uv run --env-file .env python -m ch05.run --native  # real model, native structured output
"""

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from ch05.claims import extract_claim, load_claims
from ch05.extract import Attempt, Extraction, ExtractionFailed
from ch05.fake_model import FakeModelClient
from ch05.model_client import ModelClient
from ch05.models import ExpenseClaim
from ch05.policy import PolicyFlag, check_claim, fetch_policy
from ch05.settings import Settings

DEMO_REPLIES = Path(__file__).parent / "demo_replies.json"
DEMO_ENV = {"MODEL": "fake", "INPUT_PRICE_PER_MTOK": "1", "OUTPUT_PRICE_PER_MTOK": "1"}
TODAY = date(2025, 12, 16)  # the seeded data covers 2025, so the examples fix "today"


@dataclass(frozen=True)
class Row:
    claim_id: str
    extraction: Extraction[ExpenseClaim]
    flags: list[PolicyFlag]


def demo_client() -> FakeModelClient:
    replies: dict[str, list[str]] = json.loads(DEMO_REPLIES.read_text(encoding="utf-8"))
    return FakeModelClient([reply for claim_id, _ in load_claims() for reply in replies[claim_id]])


def real_client(settings: Settings, native: bool) -> ModelClient:
    if settings.api_key is None:
        raise SystemExit("error: set ANTHROPIC_API_KEY in .env, or run with --demo")
    from ch05.anthropic_adapter import AnthropicAdapter  # the SDK is imported only here

    return AnthropicAdapter(settings, output_format=ExpenseClaim if native else None)


def print_report(rows: list[Row], failures: list[tuple[str, ExtractionFailed]]) -> None:
    print(f"{'claim':<9} {'category':<10} {'amount':<11} {'receipt':<8} {'attempts':<9} flags")
    for row in sorted(rows, key=lambda r: (not r.flags, r.claim_id)):  # flagged claims first
        c = row.extraction.value
        amount = f"{c.amount:.2f} {c.currency or '?'}"
        receipt = "yes" if c.receipt_attached else "no"
        print(f"{row.claim_id:<9} {c.category:<10} {amount:<11} {receipt:<8} "
              f"{len(row.extraction.attempts):<9} {', '.join(row.flags) or '-'}")  # fmt: skip
    for claim_id, exc in failures:
        print(f"{claim_id:<9} FAILED: {exc}")
    attempts: list[Attempt] = [a for r in rows for a in r.extraction.attempts]
    attempts += [a for _, exc in failures for a in exc.attempts]
    tokens = sum(a.input_tokens + a.output_tokens for a in attempts)
    print(f"{len(attempts)} model calls, {tokens} tokens (failed attempts included)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo", action="store_true", help="use the scripted fake model")
    parser.add_argument("--native", action="store_true", help="native structured output")
    args = parser.parse_args()

    settings = Settings.from_env({**DEMO_ENV, **os.environ} if args.demo else os.environ)
    client = demo_client() if args.demo else real_client(settings, args.native)
    with httpx.Client(base_url=settings.kestrel_url, timeout=5.0) as http:
        rules = fetch_policy(http)  # GET /policies/expense-policy

    rows: list[Row] = []
    failures: list[tuple[str, ExtractionFailed]] = []
    for claim_id, text in load_claims():
        try:
            extraction = extract_claim(
                client, text, max_attempts=settings.max_extraction_attempts,
                max_tokens=settings.max_output_tokens, today=TODAY,
            )  # fmt: skip
        except ExtractionFailed as exc:  # a bad claim goes on the list; the batch carries on
            failures.append((claim_id, exc))
            continue
        rows.append(Row(claim_id, extraction, check_claim(extraction.value, rules)))
    print_report(rows, failures)


if __name__ == "__main__":
    main()
