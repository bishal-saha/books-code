"""Copied from Chapter 13: model configurations from models.toml, and the client each one builds.

Price now comes from ch15/pricing.py (Chapter 14), so there is one Price class in this folder.

A configuration is a provider, the environment variables that hold its model name, key and
base URL, an optional reasoning effort, and its price. Model names and keys stay in .env.
"""

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr

from ch15.anthropic_adapter import AnthropicAdapter
from ch15.model_client import ModelClient
from ch15.openai_compatible_adapter import OpenAICompatibleAdapter
from ch15.pricing import Price
from ch15.settings import Settings


class ConfigError(Exception):
    """A configuration that cannot run as written. The harness skips it and says why."""


class ModelConfig(BaseModel):
    name: str
    provider: Literal["anthropic", "openai_compatible"]
    model_env: str  # the environment variable holding the model name
    api_key_env: str
    base_url_env: str | None = None  # openai_compatible only
    reasoning_effort: str | None = None  # openai_compatible only; values depend on the model
    max_tokens_param: str = "max_tokens"  # openai_compatible: the output-limit field's name
    price: Price | None = None  # None: reported as unpriced, never as free


def load_configs(path: Path) -> list[ModelConfig]:
    with path.open("rb") as f:
        return [ModelConfig(**entry) for entry in tomllib.load(f)["config"]]


def missing_env(config: ModelConfig, env: Mapping[str, str]) -> list[str]:
    names = [config.model_env, config.api_key_env, config.base_url_env]
    return [n for n in names if n and not env.get(n)]


def make_client(
    config: ModelConfig, settings: Settings, env: Mapping[str, str] = os.environ
) -> ModelClient:
    if missing := missing_env(config, env):
        raise ConfigError(f"not configured ({', '.join(missing)} empty)")
    if config.provider == "anthropic":
        if config.reasoning_effort:  # fail at startup rather than drop the setting silently
            raise ConfigError("reasoning_effort is only wired for openai_compatible here")
        return AnthropicAdapter(
            settings.model_copy(
                update={
                    "model": env[config.model_env],
                    "api_key": SecretStr(env[config.api_key_env]),
                }
            )
        )
    if not config.base_url_env:
        raise ConfigError("openai_compatible needs base_url_env")
    return OpenAICompatibleAdapter(
        settings,
        base_url=env[config.base_url_env],
        api_key=env[config.api_key_env],
        model=env[config.model_env],
        reasoning_effort=config.reasoning_effort,
        max_tokens_param=config.max_tokens_param,
    )
