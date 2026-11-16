"""The policy rules: no model anywhere. The policy itself comes from the seeded mock API."""

import typing
from datetime import date
from decimal import Decimal

import httpx
import pytest
from ch05.models import Category, ExpenseClaim
from ch05.policy import CategoryRule, PolicyFlag, check_claim, fetch_policy

RULES = {
    "meals": CategoryRule(limit=Decimal("90"), receipt_over=Decimal("25")),
    "equipment": CategoryRule(limit=Decimal("1200"), receipt_over=None),
}


def claim(**changes: object) -> ExpenseClaim:
    fields: dict[str, object] = {
        "claimant": "Daniel Reyes", "expense_date": date(2025, 11, 3), "merchant": None,
        "category": "meals", "amount": Decimal("60"), "currency": "USD",
        "receipt_attached": True, "description": "Lunch.", "attendees": None,
    }  # fmt: skip
    return ExpenseClaim(**(fields | changes))


def test_policy_from_the_mock_covers_every_category(kestrel_url: str) -> None:
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        rules = fetch_policy(http)
    assert set(rules) == set(typing.get_args(Category))
    assert rules["meals"] == CategoryRule(limit=Decimal("90"), receipt_over=Decimal("25"))
    assert rules["equipment"] == CategoryRule(limit=Decimal("1200"), receipt_over=None)


@pytest.mark.parametrize(
    "changes, flags",
    [
        ({}, []),
        ({"amount": Decimal("142.60")}, [PolicyFlag.OVER_LIMIT]),
        ({"receipt_attached": False}, [PolicyFlag.MISSING_RECEIPT]),
        ({"amount": Decimal("20"), "receipt_attached": False}, []),
        ({"category": "equipment", "amount": Decimal("20"), "receipt_attached": False},
         [PolicyFlag.MISSING_RECEIPT]),
        ({"currency": "EUR", "amount": Decimal("310")}, [PolicyFlag.NEEDS_CONVERSION]),
        ({"currency": None}, [PolicyFlag.MISSING_DETAILS]),
        ({"expense_date": None}, [PolicyFlag.MISSING_DETAILS]),
    ],
)  # fmt: skip
def test_flags(changes: dict[str, object], flags: list[PolicyFlag]) -> None:
    assert check_claim(claim(**changes), RULES) == flags
