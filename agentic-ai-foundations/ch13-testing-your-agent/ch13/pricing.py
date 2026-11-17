"""Chapter 11's cost of a call, from the usage a provider reports and a configured price."""

from decimal import Decimal

from ch13.configs import Price
from ch13.model_client import Usage

MTOK = Decimal(1_000_000)


def cost_of(usage: Usage, price: Price | None) -> Decimal | None:
    """None means unpriced. Callers show it as unpriced, never as zero."""
    if price is None:
        return None
    return (
        usage.input_tokens * price.input_per_mtok + usage.output_tokens * price.output_per_mtok
    ) / MTOK
