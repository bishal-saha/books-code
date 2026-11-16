"""Everything that can change lives here, read from environment variables (as in Chapter 3)."""

import os

from pydantic import BaseModel, SecretStr

DEFAULT_KESTREL_URL = "http://127.0.0.1:8700"  # the single Kestrel mock server


class Settings(BaseModel):
    model: str  # a current model from your provider
    api_key: SecretStr | None  # None: only the fake model can run
    max_output_tokens: int = 1024
    timeout_seconds: float = 30.0
    max_retries: int = 2
    kestrel_url: str = DEFAULT_KESTREL_URL

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        key = env.get("ANTHROPIC_API_KEY") or None  # an empty value means no key
        return cls(
            model=env.get("MODEL", ""),
            api_key=SecretStr(key) if key else None,
            max_output_tokens=int(env.get("MAX_OUTPUT_TOKENS", "1024")),
            timeout_seconds=float(env.get("MODEL_TIMEOUT_S", "30")),
            max_retries=int(env.get("MAX_RETRIES", "2")),
            kestrel_url=env.get("KESTREL_URL", DEFAULT_KESTREL_URL),
        )
