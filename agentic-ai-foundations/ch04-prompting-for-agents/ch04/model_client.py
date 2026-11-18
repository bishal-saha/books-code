"""The provider-neutral model client from Chapter 3, trimmed to what this chapter uses.

Chapter 3 also has `stream()` and the per-call cost function; nothing here needs them.
"""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

from ch04.settings import Settings

StopReason = Literal["finished", "truncated", "tool_call", "other"]
ErrorKind = Literal["timeout", "rate_limited", "auth", "bad_request", "provider_error"]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class ModelResponse(BaseModel):
    text: str
    stop_reason: StopReason
    usage: Usage


class ModelError(Exception):
    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class ModelClient(Protocol):
    def complete(
        self, system: str, messages: Sequence[Message], max_tokens: int
    ) -> ModelResponse: ...


def build_client(settings: Settings) -> ModelClient:
    """The only place that picks an adapter; the SDK is imported only when it is needed."""
    if settings.api_key is None or not settings.model:
        raise SystemExit("set ANTHROPIC_API_KEY and MODEL (see .env.example)")
    from ch04.anthropic_adapter import AnthropicAdapter

    return AnthropicAdapter(settings)
