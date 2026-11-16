"""Chapter 9's settings plus the context policy (new in Chapter 10), all from the environment."""

import os
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from ch10.state import ContextPolicy

DEFAULT_KESTREL_URL = "http://127.0.0.1:8700"  # the single Kestrel mock server

ENV_VARS = {  # environment variable -> Settings field
    "MODEL": "model",
    "ANTHROPIC_API_KEY": "api_key",
    "INPUT_PRICE_PER_MTOK": "input_price_per_mtok",
    "OUTPUT_PRICE_PER_MTOK": "output_price_per_mtok",
    "MAX_OUTPUT_TOKENS": "max_output_tokens",
    "MODEL_TIMEOUT_S": "timeout_seconds",
    "MAX_RETRIES": "max_retries",
    "KESTREL_URL": "kestrel_url",
    "RUN_MAX_STEPS": "run_max_steps",  # new in Chapter 7: the run budget
    "RUN_MAX_TOKENS": "run_max_tokens",
    "RUN_MAX_SECONDS": "run_max_seconds",
    "CONTEXT_WINDOW": "context_window",  # new in Chapter 9: the context budget
    "TOOL_RESULT_MAX_CHARS": "tool_result_max_chars",
    "SYSTEM_CEILING_TOKENS": "system_ceiling_tokens",
    "TOOLS_CEILING_TOKENS": "tools_ceiling_tokens",
    "CHARS_PER_TOKEN": "chars_per_token",
    "CONTEXT_STRATEGY": "context_strategy",  # new in Chapter 10: the context policy
    "TRIM_TARGET_TOKENS": "trim_target_tokens",
    "COMPACTION_THRESHOLD_TOKENS": "compaction_threshold_tokens",
    "COMPACTION_KEEP_UNITS": "compaction_keep_units",
    "COMPACTION_MAX_TOKENS": "compaction_max_tokens",
}


class Settings(BaseModel):
    model: str  # a current model from your provider
    api_key: SecretStr | None = None  # None: only the fake model can run
    input_price_per_mtok: Decimal = Field(gt=0)  # USD per million input tokens
    output_price_per_mtok: Decimal = Field(gt=0)  # USD per million output tokens
    max_output_tokens: int = Field(default=1024, gt=0)  # per model call
    timeout_seconds: float = Field(default=30.0, gt=0)  # per model call
    max_retries: int = Field(default=1, ge=0)  # the SDK's transport retries; 1 inside a loop
    kestrel_url: str = DEFAULT_KESTREL_URL
    run_max_steps: int = Field(default=8, gt=0)
    run_max_tokens: int = Field(default=60_000, gt=0)
    run_max_seconds: float = Field(default=90.0, gt=0)
    context_window: int = Field(default=100_000, gt=0)  # placeholder: your model's window
    tool_result_max_chars: int = Field(default=16_000, ge=256)  # enforced cap per tool result
    system_ceiling_tokens: int = Field(default=2_000, gt=0)  # warning only
    tools_ceiling_tokens: int = Field(default=3_000, gt=0)  # warning only
    chars_per_token: float = Field(default=4.0, gt=0)  # local estimates only; tune it
    context_strategy: Literal["trim", "compact"] = "trim"  # new in Chapter 10
    trim_target_tokens: int = Field(default=60_000, gt=0)  # placeholder: derive it
    compaction_threshold_tokens: int = Field(default=40_000, gt=0)
    compaction_keep_units: int = Field(default=4, ge=1)
    compaction_max_tokens: int = Field(default=1_000, gt=0)

    def context_policy(self) -> ContextPolicy:
        """New in Chapter 10. Raises if the threshold is not below the trim target."""
        return ContextPolicy(
            strategy=self.context_strategy,
            trim_target_tokens=self.trim_target_tokens,
            compaction_threshold_tokens=self.compaction_threshold_tokens,
            compaction_keep_units=self.compaction_keep_units,
            compaction_max_tokens=self.compaction_max_tokens,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Unset or empty variables are left out, so a default or a validation error applies."""
        return cls(**{field: env[var] for var, field in ENV_VARS.items() if env.get(var)})
