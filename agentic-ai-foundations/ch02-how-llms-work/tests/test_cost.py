from decimal import Decimal

from ch02.cost import estimate_cost, run_cost_table


def test_a_million_tokens_cost_the_configured_price(settings):
    estimate = estimate_cost(1_000_000, 1_000_000, settings)
    assert estimate.input_cost == settings.input_price_per_mtok
    assert estimate.output_cost == settings.output_price_per_mtok
    assert estimate.total == estimate.input_cost + estimate.output_cost


def test_small_amounts_stay_exact(settings):
    one_call = estimate_cost(150, 20, settings).total
    assert sum([one_call] * 1_000, Decimal(0)) == estimate_cost(150_000, 20_000, settings).total


def test_the_run_table_resends_the_history(settings):
    rows = run_cost_table(2_000, 1_500, 300, steps=5, settings=settings)
    assert [r.input_tokens for r in rows] == [2_000, 5_500, 10_500, 17_000, 25_000]
    assert rows[-1] == estimate_cost(25_000, 1_500, settings)
