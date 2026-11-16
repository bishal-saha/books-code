from decimal import Decimal

from ch02.cost import estimate_cost


def test_a_million_tokens_cost_the_configured_price(settings):
    estimate = estimate_cost(1_000_000, 1_000_000, settings)
    assert estimate.input_cost == settings.input_price_per_mtok
    assert estimate.output_cost == settings.output_price_per_mtok
    assert estimate.total == estimate.input_cost + estimate.output_cost


def test_small_amounts_stay_exact(settings):
    one_call = estimate_cost(150, 20, settings).total
    assert sum([one_call] * 1_000, Decimal(0)) == estimate_cost(150_000, 20_000, settings).total
