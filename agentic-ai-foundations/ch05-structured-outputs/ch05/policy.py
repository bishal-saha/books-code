"""Kestrel's expense policy as plain rules. The model never reads the policy; code applies it."""

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

import httpx

from ch05.models import ExpenseClaim

BASE_CURRENCY = "USD"  # the policy's limits are in US dollars
_USD = re.compile(r"USD ([\d,]+(?:\.\d+)?)")


class PolicyFlag(StrEnum):
    OVER_LIMIT = "OVER_LIMIT"
    MISSING_RECEIPT = "MISSING_RECEIPT"
    NEEDS_CONVERSION = "NEEDS_CONVERSION"
    MISSING_DETAILS = "MISSING_DETAILS"


@dataclass(frozen=True)
class CategoryRule:
    limit: Decimal  # per claim, in USD
    receipt_over: Decimal | None  # None: a receipt is always required


def _usd(cell: str) -> Decimal:
    match = _USD.search(cell)
    if match is None:
        raise ValueError(f"no USD amount in policy cell {cell!r}")
    return Decimal(match.group(1).replace(",", ""))


def parse_policy(body: str) -> dict[str, CategoryRule]:
    """Read the policy's table: | Category | Limit per claim | Receipt required | Approver |."""
    rules: dict[str, CategoryRule] = {}
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("Category", "") or set(cells[0]) <= set("-"):
            continue
        receipt = None if cells[2].lower() == "always" else _usd(cells[2])
        rules[cells[0].lower()] = CategoryRule(limit=_usd(cells[1]), receipt_over=receipt)
    if not rules:
        raise ValueError("the expense policy has no category table")
    return rules


def fetch_policy(http: httpx.Client) -> dict[str, CategoryRule]:
    response = http.get("/policies/expense-policy")
    response.raise_for_status()
    return parse_policy(response.json()["body"])


def check_claim(claim: ExpenseClaim, rules: dict[str, CategoryRule]) -> list[PolicyFlag]:
    rule = rules[claim.category]  # every Category value is a policy row (test_policy.py checks)
    in_usd = claim.currency == BASE_CURRENCY  # never compare a euro amount with a dollar limit
    flags: list[PolicyFlag] = []
    if claim.currency is None or claim.expense_date is None:
        flags.append(PolicyFlag.MISSING_DETAILS)
    if claim.currency is not None and not in_usd:
        flags.append(PolicyFlag.NEEDS_CONVERSION)
    needs_receipt = rule.receipt_over is None or (in_usd and claim.amount > rule.receipt_over)
    if needs_receipt and not claim.receipt_attached:
        flags.append(PolicyFlag.MISSING_RECEIPT)
    if in_usd and claim.amount > rule.limit:
        flags.append(PolicyFlag.OVER_LIMIT)
    return flags
