"""Model prices from Chapter 11's models.toml: one price source for the whole book.

Price and cost_of are copied from Chapter 13 (ch13/configs.py, ch13/pricing.py). New in
Chapter 14: load_price reads one configuration's price without building its client, so
design_check can cost the budget walk-through. The search price stays in Settings.
"""

import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

MTOK = Decimal(1_000_000)


class Price(BaseModel):
    currency: str = "USD"
    input_per_mtok: Decimal = Field(ge=0)  # strings in the file, parsed straight to Decimal
    output_per_mtok: Decimal = Field(ge=0)
    as_of: date  # the day you read the seller's pricing page
    source_url: str  # that page


def load_price(path: Path, config: str) -> Price | None:
    """The [config.price] table of one [[config]] entry; None when it has no price."""
    with path.open("rb") as f:
        for entry in tomllib.load(f)["config"]:
            if entry["name"] == config:
                return Price(**entry["price"]) if "price" in entry else None
    raise KeyError(f"no configuration named {config!r} in {path}")


def cost_of(input_tokens: int, output_tokens: int, price: Price) -> Decimal:
    return (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / MTOK
