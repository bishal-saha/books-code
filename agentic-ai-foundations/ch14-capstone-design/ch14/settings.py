"""Chapter 13's settings, trimmed to what the research assistant uses, plus its design values.

Kept from earlier chapters: model, key, per-call limits (MODEL_TIMEOUT_S, MAX_RETRIES = 1 inside
a loop, Chapter 7), the run budget (Chapter 7), the context budget (Chapter 9), PROMPT_VERSION.
New in Chapter 14: the capstone's run budget values, the money limit (designed here, enforced
in Chapter 16), the search backend's key, timeout and price, and the sandboxed exports folder.
"""

import os
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

ENV_VARS = {  # environment variable -> Settings field
    "MODEL": "model",
    "ANTHROPIC_API_KEY": "api_key",
    "MAX_OUTPUT_TOKENS": "max_output_tokens",
    "MODEL_TIMEOUT_S": "timeout_seconds",
    "MODEL_THINKING": "model_thinking",
    "MAX_RETRIES": "max_retries",
    "RUN_MAX_STEPS": "run_max_steps",
    "RUN_MAX_TOKENS": "run_max_tokens",
    "RUN_MAX_SECONDS": "run_max_seconds",
    "RUN_MAX_COST_USD": "run_max_cost_usd",  # new in Chapter 14
    "TOOL_RESULT_MAX_CHARS": "tool_result_max_chars",
    "CHARS_PER_TOKEN": "chars_per_token",
    "PROMPT_VERSION": "prompt_version",
    "SEARCH_API_KEY": "search_api_key",  # new in Chapter 14
    "SEARCH_TIMEOUT_S": "search_timeout_s",
    "SEARCH_USD_PER_QUERY": "search_usd_per_query",
    "EXPORTS_DIR": "exports_dir",
}


class Settings(BaseModel):
    model: str | None = None  # a current model from your provider with tool calling
    api_key: SecretStr | None = None  # None: only the fake model can run
    max_output_tokens: int = Field(default=1024, gt=0)  # per model call
    timeout_seconds: float = Field(default=30.0, gt=0)  # per model call; the loop shrinks it
    max_retries: int = Field(default=1, ge=0)  # SDK transport retries: 1 inside a loop
    # "off": Chapter 3's adapter sends thinking={"type": "disabled"}; "adaptive" sends nothing.
    # No adapter in this folder; Chapter 15 copies it back and reads this field.
    model_thinking: Literal["off", "adaptive"] = "off"
    # The run budget for one question (design values; tune them from your own traces)
    run_max_steps: int = Field(default=8, gt=0)
    run_max_tokens: int = Field(default=60_000, gt=0)
    run_max_seconds: float = Field(default=120.0, gt=0)
    run_max_cost_usd: Decimal = Field(default=Decimal("0.50"), gt=0)  # enforced from Chapter 16
    tool_result_max_chars: int = Field(default=16_000, ge=256)  # Chapter 9's enforced cap
    chars_per_token: float = Field(default=4.0, gt=0)  # local token estimates only
    prompt_version: int = Field(default=1, ge=1)  # prompts/research_assistant_v<N>.md
    search_api_key: SecretStr | None = None  # sent in a request header, never in a URL
    search_timeout_s: float = Field(default=10.0, gt=0)  # capped by the run's time left
    search_usd_per_query: Decimal | None = None  # from your search provider's price page
    exports_dir: Path = Path(".kestrel/exports")  # the file sandbox root

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Unset or empty variables are left out, so a default or a validation error applies."""
        return cls(**{field: env[var] for var, field in ENV_VARS.items() if env.get(var)})
