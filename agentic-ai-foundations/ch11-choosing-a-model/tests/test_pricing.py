"""Prices as configuration: Decimal arithmetic, unpriced never shown as zero, the example file."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from ch11.agent import RunResult, StepRecord
from ch11.budget import StopCause
from ch11.configs import Price, load_configs
from ch11.model_client import Usage
from ch11.pricing import cost_of, next_call_ceiling, run_cost
from pydantic import ValidationError

FOLDER = Path(__file__).parent.parent


def make_price(input_per_mtok: str, output_per_mtok: str) -> Price:
    return Price(
        input_per_mtok=input_per_mtok,
        output_per_mtok=output_per_mtok,
        as_of=date(2026, 11, 16),
        source_url="test",
    )


def step(index: int, tokens_in: int, tokens_out: int) -> StepRecord:
    return StepRecord(index=index, messages_sent=1, max_output_tokens=512, timeout_seconds=30.0,
                      stop_reason="tool_call", tool_calls=[], input_tokens=tokens_in,
                      output_tokens=tokens_out, duration_ms=1)  # fmt: skip


def test_cost_of_one_call_is_exact() -> None:
    price = make_price("2", "8")
    assert cost_of(Usage(input_tokens=1_000_000, output_tokens=500_000), price) == Decimal("6")


def test_no_price_is_unpriced_not_free() -> None:
    assert cost_of(Usage(input_tokens=10, output_tokens=10), None) is None


def test_run_cost_sums_every_model_call() -> None:
    result = RunResult(cause=StopCause.FINISHED, final_text="", messages=[],
                       steps=[step(0, 400_000, 0), step(1, 600_000, 250_000)])  # fmt: skip
    assert run_cost(result, make_price("2", "8")) == Decimal("4")


def test_next_call_ceiling_assumes_the_whole_output_limit() -> None:
    assert next_call_ceiling(500_000, 1_000_000, make_price("2", "8")) == Decimal("9")


def test_example_file_refuses_to_load_until_prices_are_set() -> None:
    with pytest.raises(ValidationError):
        load_configs(FOLDER / "models.example.toml")


def test_filled_in_file_loads(tmp_path: Path) -> None:
    text = (FOLDER / "models.example.toml").read_text()
    text = text.replace('as_of = "SET-ME"', 'as_of = "2026-11-16"').replace('"SET-ME"', '"1.50"')
    (tmp_path / "models.toml").write_text(text)
    configs = load_configs(tmp_path / "models.toml")
    assert [c.name for c in configs] == ["hosted-sdk", "hosted-compat-low-effort", "local-server"]
    assert configs[0].price.input_per_mtok == Decimal("1.50")
    assert configs[2].price is None
