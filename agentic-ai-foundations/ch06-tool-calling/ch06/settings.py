"""Chapter 3's settings, unchanged: everything that can change, read from environment variables."""

import os
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

DEFAULT_KESTREL_URL = "http://127.0.0.1:8700"  # the single Kestrel mock server

ENV_VARS = {  # environment variable -> Settings field
    "MODEL": "model",
    "ANTHROPIC_API_KEY": "api_key",
    "INPUT_PRICE_PER_MTOK": "input_price_per_mtok",
    "OUTPUT_PRICE_PER_MTOK": "output_price_per_mtok",
    "MAX_OUTPUT_TOKENS": "max_output_tokens",
    "MODEL_TIMEOUT_S": "timeout_seconds",
    "MAX_RETRIES": "max_retries",
    "MODEL_THINKING": "thinking",
    "KESTREL_URL": "kestrel_url",
}


class Settings(BaseModel):
    model: str  # a current model from your provider
    api_key: SecretStr | None = None  # None: only the fake model can run
    input_price_per_mtok: Decimal = Field(gt=0)  # USD per million input tokens
    output_price_per_mtok: Decimal = Field(gt=0)  # USD per million output tokens
    max_output_tokens: int = Field(default=400, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0)  # the SDK's transport retries (Chapter 3)
    thinking: Literal["off", "adaptive"] = "off"  # off: the adapter disables thinking
    kestrel_url: str = DEFAULT_KESTREL_URL

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Unset or empty variables are left out, so a default or a validation error applies."""
        return cls(**{field: env[var] for var, field in ENV_VARS.items() if env.get(var)})
