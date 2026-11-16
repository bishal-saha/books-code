"""The output contract: the generated schema and the meaning-layer validator."""

from datetime import date
from decimal import Decimal

import pytest
from ch05.models import ExpenseClaim
from ch05.sample_replies import FUTURE_DATE_JSON, TODAY, VALID_JSON
from pydantic import ValidationError


def test_schema_lists_required_fields_and_category_enum() -> None:
    schema = ExpenseClaim.model_json_schema()
    assert {"claimant", "expense_date", "merchant", "amount", "currency"} <= set(schema["required"])
    assert schema["properties"]["category"]["enum"] == [
        "travel", "meals", "software", "equipment", "training",
    ]  # fmt: skip
    assert schema["additionalProperties"] is False


def test_amount_is_a_decimal() -> None:
    claim = ExpenseClaim.model_validate_json(VALID_JSON, context={"today": TODAY})
    assert claim.amount == Decimal("142.60")


def test_a_future_date_fails_against_the_given_today() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExpenseClaim.model_validate_json(FUTURE_DATE_JSON, context={"today": TODAY})
    assert exc_info.value.errors()[0]["type"] == "value_error"
    # The same reply is valid on a later "today": the clock is an input, not a hidden global.
    assert ExpenseClaim.model_validate_json(FUTURE_DATE_JSON, context={"today": date(2026, 2, 1)})
