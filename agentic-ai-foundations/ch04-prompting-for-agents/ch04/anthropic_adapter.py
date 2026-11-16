"""The Anthropic adapter from Chapter 3 (complete() only). The only file that imports the SDK."""

from collections.abc import Sequence

import anthropic

from ch04.model_client import Message, ModelError, ModelResponse, StopReason, Usage
from ch04.settings import Settings

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "finished",
    "max_tokens": "truncated",
    "tool_use": "tool_call",
}


class AnthropicAdapter:
    def __init__(self, settings: Settings) -> None:
        assert settings.api_key is not None
        self._model = settings.model
        self._client = anthropic.Anthropic(
            api_key=settings.api_key.get_secret_value(),
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except anthropic.APIError as exc:
            raise _to_model_error(exc) from exc
        return ModelResponse(
            text="".join(b.text for b in response.content if b.type == "text"),
            stop_reason=_STOP_REASONS.get(response.stop_reason or "", "other"),
            usage=Usage(
                input_tokens=response.usage.input_tokens
                + (response.usage.cache_creation_input_tokens or 0)
                + (response.usage.cache_read_input_tokens or 0),
                output_tokens=response.usage.output_tokens,
            ),
        )


def _to_model_error(exc: anthropic.APIError) -> ModelError:
    if isinstance(exc, anthropic.APITimeoutError):  # check before its parent class
        return ModelError("timeout", "the request timed out")
    if isinstance(exc, anthropic.APIConnectionError):
        return ModelError("provider_error", "could not reach the provider")
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ModelError("auth", "the API key was rejected")
    if isinstance(exc, anthropic.RateLimitError):
        return ModelError("rate_limited", "the provider is rate limiting this key")
    if isinstance(exc, anthropic.BadRequestError):
        return ModelError("bad_request", "the provider rejected the request")
    return ModelError("provider_error", "the provider returned an error")
