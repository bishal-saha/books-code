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


def run_cost_table(
    start: int, new_per_step: int, output_per_step: int, steps: int, settings: Settings
) -> list[CostEstimate]:
    """Cumulative cost after each step of a run that resends its whole history every call."""
    rows: list[CostEstimate] = []
    total_in = total_out = 0
    for step in range(steps):
        total_in += start + step * new_per_step  # this call's input
        total_out += output_per_step
        rows.append(estimate_cost(total_in, total_out, settings))
    return rows
