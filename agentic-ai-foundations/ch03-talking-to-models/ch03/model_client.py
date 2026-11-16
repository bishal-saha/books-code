"""The provider-neutral model client: the book's own types and build_client()."""

from collections.abc import Iterator, Sequence
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel

from ch03.settings import Settings

StopReason = Literal["finished", "truncated", "tool_call", "other"]
ErrorKind = Literal["timeout", "rate_limited", "auth", "bad_request", "provider_error"]
PER_MILLION = Decimal(1_000_000)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Usage(BaseModel):
    input_tokens: int  # all input, cached tokens included
    output_tokens: int


class ModelResponse(BaseModel):
    text: str
    stop_reason: StopReason
    usage: Usage
    request_id: str | None = None


class ModelError(Exception):
    def __init__(self, kind: ErrorKind, message: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.request_id = request_id


class ModelClient(Protocol):
    def complete(
        self, system: str, messages: Sequence[Message], max_tokens: int
    ) -> ModelResponse: ...

    def stream(
        self, system: str, messages: Sequence[Message], max_tokens: int
    ) -> Iterator[str | ModelResponse]:
        """Yield text chunks as they arrive, then one final ModelResponse."""
        ...


def call_cost_usd(usage: Usage, settings: Settings) -> Decimal:
    input_cost = usage.input_tokens * settings.input_price_per_mtok / PER_MILLION
    output_cost = usage.output_tokens * settings.output_price_per_mtok / PER_MILLION
    return input_cost + output_cost


def build_client(settings: Settings) -> ModelClient:
    """The only place that picks an adapter; the SDK is imported only when it is needed."""
    if settings.api_key is None:
        raise SystemExit("error: set ANTHROPIC_API_KEY in .env (tests use the fake model)")
    from ch03.anthropic_adapter import AnthropicAdapter

    return AnthropicAdapter(settings)
