"""The cost of a call and of a run, from the usage a provider reports and a configured price."""

from decimal import Decimal

from ch11.agent import RunResult
from ch11.configs import Price
from ch11.model_client import Usage

MTOK = Decimal(1_000_000)


def cost_of(usage: Usage, price: Price | None) -> Decimal | None:
    """None means unpriced. Callers show it as unpriced, never as zero."""
    if price is None:
        return None
    return (
        usage.input_tokens * price.input_per_mtok + usage.output_tokens * price.output_per_mtok
    ) / MTOK


def run_cost(result: RunResult, price: Price | None) -> Decimal | None:
    """Every model call in Chapter 7's step log, summed: cost per run, not per call."""
    used = Usage(
        input_tokens=sum(s.input_tokens for s in result.steps),
        output_tokens=sum(s.output_tokens for s in result.steps),
    )
    return cost_of(used, price)


def next_call_ceiling(input_tokens: int, max_output_tokens: int, price: Price) -> Decimal:
    """What the next call can cost if it uses its whole output limit. A money budget
    checks spend so far plus this before each call (Chapter 16 wires that in)."""
    return (input_tokens * price.input_per_mtok + max_output_tokens * price.output_per_mtok) / MTOK
