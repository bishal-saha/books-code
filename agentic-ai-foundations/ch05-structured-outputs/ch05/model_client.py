"""Chapter 3's provider-neutral model client, trimmed to complete(). Unchanged otherwise.

Stop reasons stay Chapter 3's: finished, truncated, tool_call, and other for anything an
adapter can't map (a provider refusal arrives as "other").
"""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

StopReason = Literal["finished", "truncated", "tool_call", "other"]
ErrorKind = Literal["timeout", "rate_limited", "auth", "bad_request", "provider_error"]


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
