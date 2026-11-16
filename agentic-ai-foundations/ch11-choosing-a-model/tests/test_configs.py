"""Configurations: skipped loudly when incomplete, and the preflight call."""

from datetime import date
from decimal import Decimal

import pytest
from ch11.compare_models import preflight
from ch11.configs import ConfigError, ModelConfig, Price, make_client
from ch11.fake_model import FakeModelClient
from ch11.model_client import ModelError
from ch11.openai_compatible_adapter import OpenAICompatibleAdapter
from ch11.settings import Settings

COMPAT = ModelConfig(name="compat", provider="openai_compatible", model_env="M",
                     api_key_env="K", base_url_env="U", reasoning_effort="low")  # fmt: skip
ENV = {"M": "some-model", "K": "key", "U": "https://compat.example.com/v1"}


def test_empty_variable_means_not_configured() -> None:
    with pytest.raises(ConfigError, match=r"not configured \(K empty\)"):
        make_client(COMPAT, Settings(), {**ENV, "K": ""})


def test_compatible_config_builds_the_httpx_adapter() -> None:
    assert isinstance(make_client(COMPAT, Settings(), ENV), OpenAICompatibleAdapter)


def test_effort_on_the_anthropic_adapter_fails_at_startup() -> None:
    config = ModelConfig(name="sdk", provider="anthropic", model_env="M", api_key_env="K",
                         reasoning_effort="high")  # fmt: skip
    with pytest.raises(ConfigError, match="reasoning_effort"):
        make_client(config, Settings(), ENV)


def test_price_strings_parse_to_decimal() -> None:
    price = Price(input_per_mtok="0.10", output_per_mtok="0.40", as_of=date(2026, 11, 16),
                  source_url="x")  # fmt: skip
    assert price.input_per_mtok == Decimal("0.10")


@pytest.mark.parametrize("kind", ["auth", "bad_request"])
def test_preflight_rejection_is_a_configuration_error(kind: str) -> None:
    with pytest.raises(ConfigError, match="preflight rejected"):
        preflight(FakeModelClient([ModelError(kind, "rejected")]))


def test_preflight_lets_a_timeout_through() -> None:
    preflight(FakeModelClient([ModelError("timeout", "slow")]))  # the runs will show it
