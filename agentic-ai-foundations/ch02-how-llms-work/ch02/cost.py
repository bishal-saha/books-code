"""Token-based cost from configured prices. No price appears as a literal."""

from decimal import Decimal

from pydantic import BaseModel

from ch02.settings import Settings

PER_MILLION = Decimal(1_000_000)


class CostEstimate(BaseModel):
    input_tokens: int
    output_tokens: int
    input_cost: Decimal
    output_cost: Decimal

    @property
    def total(self) -> Decimal:
        return self.input_cost + self.output_cost


def estimate_cost(input_tokens: int, output_tokens: int, settings: Settings) -> CostEstimate:
    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost=input_tokens * settings.input_price_per_mtok / PER_MILLION,
        output_cost=output_tokens * settings.output_price_per_mtok / PER_MILLION,
    )
