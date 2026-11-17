"""Chapter 15's settings, plus Chapter 16's search retries and Chapter 13's eval settings.

Kept from Chapter 14: model, key, per-call limits (MODEL_TIMEOUT_S, MAX_RETRIES = 1 inside a
loop), the capstone run budget, RUN_MAX_COST_USD (enforced from Chapter 16), the search key,
timeout and price, and the sandboxed exports folder.
New in Chapter 15: SEARCH_ENDPOINT (empty: search_web reports that search isn't configured)
and Chapter 10's context policy (CONTEXT_STRATEGY and the compaction settings).
New in Chapter 16: RUN_MAX_COST_USD is enforced (the price comes from models.toml), the
search retry policy (SEARCH_RETRY_ATTEMPTS, SEARCH_RETRY_BASE_S, SEARCH_RETRY_CAP_S), and
Chapter 13's eval settings (EVAL_TRIALS, EVAL_MAX_COST_USD) for ch16.eval.
"""

import os
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from ch16.retry import RetryPolicy
from ch16.state import ContextPolicy

ENV_VARS = {  # environment variable -> Settings field
    "MODEL": "model",
    "ANTHROPIC_API_KEY": "api_key",
    "MAX_OUTPUT_TOKENS": "max_output_tokens",
    "MODEL_TIMEOUT_S": "timeout_seconds",
    "MAX_RETRIES": "max_retries",
    "RUN_MAX_STEPS": "run_max_steps",
    "RUN_MAX_TOKENS": "run_max_tokens",
    "RUN_MAX_SECONDS": "run_max_seconds",
    "RUN_MAX_COST_USD": "run_max_cost_usd",
    "TOOL_RESULT_MAX_CHARS": "tool_result_max_chars",
    "CHARS_PER_TOKEN": "chars_per_token",
    "PROMPT_VERSION": "prompt_version",
    "SEARCH_ENDPOINT": "search_endpoint",  # new in Chapter 15
    "SEARCH_API_KEY": "search_api_key",
    "SEARCH_TIMEOUT_S": "search_timeout_s",
    "SEARCH_USD_PER_QUERY": "search_usd_per_query",
    "EXPORTS_DIR": "exports_dir",
    "SEARCH_RETRY_ATTEMPTS": "search_retry_attempts",  # new in Chapter 16
    "SEARCH_RETRY_BASE_S": "search_retry_base_s",
    "SEARCH_RETRY_CAP_S": "search_retry_cap_s",
    "EVAL_TRIALS": "eval_trials",  # Chapter 13's eval settings
    "EVAL_MAX_COST_USD": "eval_max_cost_usd",
    "CONTEXT_STRATEGY": "context_strategy",  # new in Chapter 15: Chapter 10's policy
    "TRIM_TARGET_TOKENS": "trim_target_tokens",
    "COMPACTION_THRESHOLD_TOKENS": "compaction_threshold_tokens",
    "COMPACTION_KEEP_UNITS": "compaction_keep_units",
    "COMPACTION_MAX_TOKENS": "compaction_max_tokens",
}


class Settings(BaseModel):
    model: str | None = None  # a current model from your provider with tool calling
    api_key: SecretStr | None = None  # None: only the fake model can run
    max_output_tokens: int = Field(default=1024, gt=0)  # per model call
    timeout_seconds: float = Field(default=30.0, gt=0)  # per model call; the loop shrinks it
    max_retries: int = Field(default=1, ge=0)  # SDK transport retries: 1 inside a loop
    # The run budget for one question (Chapter 14's design values)
    run_max_steps: int = Field(default=8, gt=0)
    run_max_tokens: int = Field(default=60_000, gt=0)
    run_max_seconds: float = Field(default=120.0, gt=0)
    run_max_cost_usd: Decimal = Field(default=Decimal("0.50"), gt=0)  # enforced from Chapter 16
    tool_result_max_chars: int = Field(default=16_000, ge=256)  # Chapter 9's enforced cap
    chars_per_token: float = Field(default=4.0, gt=0)  # local token estimates only
    prompt_version: int = Field(default=1, ge=1)  # prompts/research_assistant_v<N>.md
    search_endpoint: str | None = None  # new: your search service's URL (HttpSearchBackend)
    search_api_key: SecretStr | None = None  # sent in a request header, never in a URL
    search_timeout_s: float = Field(default=10.0, gt=0)  # capped by the run's time left
    search_usd_per_query: Decimal | None = None  # from your search provider's price page
    exports_dir: Path = Path(".kestrel/exports")  # the file sandbox root
    # New in Chapter 16: retries for search_web (transient failures only)
    search_retry_attempts: int = Field(default=3, ge=1)  # the first try counts
    search_retry_base_s: float = Field(default=0.5, gt=0)
    search_retry_cap_s: float = Field(default=4.0, gt=0)
    # Chapter 13's eval settings
    eval_trials: int = Field(default=5, ge=1)  # trials per golden task
    eval_max_cost_usd: Decimal = Field(default=Decimal("0.50"), gt=0)  # the whole eval
    # New in Chapter 15: Chapter 10's context policy. A one-question run stays far below these.
    context_strategy: Literal["trim", "compact"] = "compact"
    trim_target_tokens: int = Field(default=40_000, gt=0)
    compaction_threshold_tokens: int = Field(default=24_000, gt=0)
    compaction_keep_units: int = Field(default=4, ge=1)
    compaction_max_tokens: int = Field(default=1_000, gt=0)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Unset or empty variables are left out, so a default or a validation error applies."""
        return cls(**{field: env[var] for var, field in ENV_VARS.items() if env.get(var)})

    def context_policy(self) -> ContextPolicy:
        return ContextPolicy(
            strategy=self.context_strategy,
            trim_target_tokens=self.trim_target_tokens,
            compaction_threshold_tokens=self.compaction_threshold_tokens,
            compaction_keep_units=self.compaction_keep_units,
            compaction_max_tokens=self.compaction_max_tokens,
        )

    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            self.search_retry_attempts, self.search_retry_base_s, self.search_retry_cap_s
        )
