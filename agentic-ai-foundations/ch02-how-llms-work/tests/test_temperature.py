import math

import pytest
from ch02.temperature import SCORES, probabilities, sample


def test_probabilities_add_up_to_one():
    for temperature in (0.2, 1.0, 2.0):
        assert math.isclose(sum(probabilities(SCORES, temperature).values()), 1.0)


def test_lower_temperature_concentrates_on_the_top_token():
    tops = [probabilities(SCORES, t)["within"] for t in (0.2, 1.0, 2.0)]
    assert tops[0] > tops[1] > tops[2]  # the top token's share shrinks as temperature rises
    assert tops[0] > 0.99


def test_the_order_of_tokens_never_changes():
    for temperature in (0.2, 1.0, 2.0):
        probs = probabilities(SCORES, temperature)
        assert sorted(probs, key=probs.get, reverse=True) == list(SCORES)


def test_seeded_sampling_repeats_and_counts_every_pick():
    assert sample(SCORES, 1.0, picks=100) == sample(SCORES, 1.0, picks=100)
    assert sum(sample(SCORES, 1.0, picks=100).values()) == 100


def test_zero_temperature_is_refused():
    with pytest.raises(ValueError, match="positive"):
        probabilities(SCORES, 0)
