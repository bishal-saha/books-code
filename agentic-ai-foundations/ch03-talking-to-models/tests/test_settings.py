from decimal import Decimal

import pytest
from ch03.model_client import ConfigError, build_client
from ch03.settings import Settings
from pydantic import ValidationError

ENV = {"MODEL": "test-model", "INPUT_PRICE_PER_MTOK": "2", "OUTPUT_PRICE_PER_MTOK": "10"}


def test_defaults_apply_and_prices_are_decimal():
    settings = Settings.from_env(ENV)
    assert settings.input_price_per_mtok == Decimal("2")
    assert (settings.max_output_tokens, settings.timeout_seconds, settings.max_retries) == (
        400,
        30.0,
        2,
    )
    assert settings.api_key is None


def test_missing_settings_fail_fast_and_name_every_field():
    with pytest.raises(ValidationError) as info:
        Settings.from_env({"MODEL_TIMEOUT_S": "10"})
    missing = {e["loc"][0] for e in info.value.errors()}
    assert missing == {"model", "input_price_per_mtok", "output_price_per_mtok"}


def test_empty_values_count_as_unset_and_zero_prices_are_rejected():
    with pytest.raises(ValidationError):
        Settings.from_env({**ENV, "INPUT_PRICE_PER_MTOK": "0"})
    assert Settings.from_env({**ENV, "ANTHROPIC_API_KEY": ""}).api_key is None


def test_the_key_never_appears_in_repr():
    settings = Settings.from_env({**ENV, "ANTHROPIC_API_KEY": "sk-secret"})
    assert "sk-secret" not in repr(settings)
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "sk-secret"


def test_without_a_key_build_client_raises_config_error():
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        build_client(Settings.from_env(ENV))
