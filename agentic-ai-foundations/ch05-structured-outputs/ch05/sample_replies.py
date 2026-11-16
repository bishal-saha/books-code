"""Test data: one valid reply for claim-01, and broken variants that each differ in one way."""

import json
from datetime import date

TODAY = date(2025, 12, 16)
CLAIM_TEXT = (
    "From: Daniel Reyes\n"
    "Dinner at The Copper Kettle in Denver with two buyers from Brackenford Campsites, "
    "3 November 2025. $142.60 for the three of us. Receipt attached."
)

_VALID = {
    "claimant": "Daniel Reyes", "expense_date": "2025-11-03", "merchant": "The Copper Kettle",
    "category": "meals", "amount": 142.60, "currency": "USD", "receipt_attached": True,
    "description": "Dinner in Denver with two buyers from Brackenford Campsites.",
    "attendees": {"count": 3, "names": ["two buyers from Brackenford Campsites"]},
}  # fmt: skip

VALID_JSON = json.dumps(_VALID)
FENCED_JSON = f"```json\n{VALID_JSON}\n```"
PROSE_JSON = f"Here is the extracted claim:\n{VALID_JSON}"
MISSING_CURRENCY_JSON = json.dumps({k: v for k, v in _VALID.items() if k != "currency"})
BAD_CATEGORY_JSON = json.dumps(_VALID | {"category": "Meals & Entertainment"})
FUTURE_DATE_JSON = json.dumps(_VALID | {"expense_date": "2026-01-05"})
