"""Chapter 11's settings: everything that can change, from the environment.

Prices and each candidate's model still live in models.toml (ch13/configs.py).
New in Chapter 13: PROMPT_VERSION picks the prompt file, EVAL_TRIALS sets trials per golden
task, and EVAL_MAX_COST_USD caps what one whole eval may spend. COMPARE_RUNS is gone.
"""

import os
from collections.abc import Mapping
from decimal import Decimal

from pydantic import BaseModel, Field, SecretStr

DEFAULT_KESTREL_URL = "http://127.0.0.1:8700"  # the single Kestrel mock server

ENV_VARS = {  # environment variable -> Settings field
    "MODEL": "model",
    "ANTHROPIC_API_KEY": "api_key",
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
    "PROMPT_VERSION": "prompt_version",  # new in Chapter 13
    "EVAL_TRIALS": "eval_trials",
    "EVAL_MAX_COST_USD": "eval_max_cost_usd",
}


class Settings(BaseModel):
    model: str | None = None  # Chapter 11: each configuration supplies its own
    api_key: SecretStr | None = None  # None: only the fake model can run
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
    prompt_version: int = Field(default=1, ge=1)  # prompts/operations_v<N>.md
    eval_trials: int = Field(default=5, ge=1)  # trials per golden task
    eval_max_cost_usd: Decimal = Field(default=Decimal("0.50"), gt=0)  # the whole eval

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Unset or empty variables are left out, so a default or a validation error applies."""
        return cls(**{field: env[var] for var, field in ENV_VARS.items() if env.get(var)})
