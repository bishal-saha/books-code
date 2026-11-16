"""Everything that can change lives here, read from environment variables."""

import os
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, SecretStr


class Settings(BaseModel):
    model: str  # a current model from your provider
    api_key: SecretStr | None  # None: counting falls back to the labelled estimate
    input_price_per_mtok: Decimal  # USD per million input tokens
    output_price_per_mtok: Decimal  # USD per million output tokens
    context_window_tokens: int  # from your provider's docs for this model
    docs_dir: Path  # Markdown docs written by `uv run kestrel up`
    model_timeout_s: float

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        key = env.get("ANTHROPIC_API_KEY") or None  # an empty value means no key
        return cls(
            model=env["MODEL"],
            api_key=SecretStr(key) if key else None,
            input_price_per_mtok=Decimal(env["INPUT_PRICE_PER_MTOK"]),
            output_price_per_mtok=Decimal(env["OUTPUT_PRICE_PER_MTOK"]),
            context_window_tokens=int(env["CONTEXT_WINDOW_TOKENS"]),
            docs_dir=Path(env.get("KESTREL_DOCS_DIR", ".kestrel/docs")),
            model_timeout_s=float(env.get("MODEL_TIMEOUT_S", "30")),
        )
