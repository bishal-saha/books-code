"""ExpenseClaim: the fields the model extracts from one free-text claim. No policy here."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

# The categories of Kestrel's expense policy (GET /policies/expense-policy), lowercased.
Category = Literal["travel", "meals", "software", "equipment", "training"]
Currency = Literal["USD", "EUR", "GBP"]


class Attendees(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=1, description="People the expense covered, including the claimant.")
    names: list[str] = Field(description="Names of the other attendees as written in the claim.")


class ExpenseClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claimant: str = Field(description="Full name of the person making the claim, as written.")
    expense_date: date | None = Field(
        description="Date the expense was incurred, YYYY-MM-DD; null if the claim gives none."
    )
    merchant: str | None = Field(description="Business paid; null if the claim names none.")
    category: Category = Field(description="Exactly one of the listed lowercase values.")
    amount: Decimal = Field(gt=0, description="Amount as written, without a currency symbol.")
    currency: Currency | None = Field(
        description="ISO code of the amount's currency; null if the claim doesn't make it clear."
    )
    receipt_attached: bool = Field(description="True only if the claim says a receipt is attached.")
    description: str = Field(description="One-sentence summary of what was bought and why.")
    attendees: Attendees | None = Field(description="Who the expense covered; null if not stated.")

    @field_validator("expense_date")
    @classmethod
    def not_in_future(cls, value: date | None, info: ValidationInfo) -> date | None:
        # The caller passes "today" in the validation context; tests and the demo fix it.
        today = (info.context or {}).get("today") or date.today()
        if value is not None and value > today:
            raise ValueError(f"expense_date {value} is after today ({today})")
        return value


if __name__ == "__main__":
    import json

    print(json.dumps(ExpenseClaim.model_json_schema(), indent=2))
