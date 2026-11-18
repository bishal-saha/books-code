import pytest
from ch02.tokens import check_fits, require_fit


def test_input_larger_than_the_window_fails_before_any_call():
    check = check_fits(12_000, max_tokens=1_024, context_window=10_000)
    assert check.input_fits is False
    assert check.fits is False
    assert check.output_headroom == 0


def test_input_fits_but_the_reserved_output_does_not():
    check = check_fits(9_500, max_tokens=1_024, context_window=10_000)
    assert check.input_fits is True
    assert check.fits is False
    assert check.output_headroom == 500


def test_headroom_is_the_largest_max_tokens_that_fits():
    check = check_fits(9_500, max_tokens=500, context_window=10_000)
    assert check.fits is True


def test_rejects_nonsense_sizes():
    with pytest.raises(ValueError):
        check_fits(100, max_tokens=0, context_window=10_000)


def test_no_provider_count_is_refused_before_any_call():
    with pytest.raises(ValueError, match="no provider count"):
        require_fit(None, max_tokens=256, context_window=10_000)
