"""Chapter 3's Anthropic adapter (complete() only), plus one Chapter 5 option: output_format.

With output_format set, every request carries the schema as output_config.format, the
provider's native structured output. Without it, requests are exactly Chapter 3's.
"""

from collections.abc import Sequence

import anthropic
from pydantic import BaseModel

from ch05.model_client import Message, ModelError, ModelResponse, StopReason, Usage
from ch05.settings import Settings

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "finished",
    "stop_sequence": "finished",
    "max_tokens": "truncated",
    "model_context_window_exceeded": "truncated",
    "tool_use": "tool_call",
}  # anything else, "refusal" included, becomes "other"


def native_format(output_format: type[BaseModel]) -> anthropic.types.JSONOutputFormatParam:
    """The schema as the API receives it: the SDK's transform, as messages.parse() applies it."""
    return {"type": "json_schema", "schema": anthropic.transform_schema(output_format)}


class AnthropicAdapter:
    def __init__(
        self,
        settings: Settings,
        output_format: type[BaseModel] | None = None,  # added in Chapter 5
        http_client: anthropic.DefaultHttpxClient | None = None,
    ) -> None:
        assert settings.api_key is not None
        self._model = settings.model
        self._output_config: anthropic.types.OutputConfigParam | None = (
            {"format": native_format(output_format)} if output_format else None
        )
        self._client = anthropic.Anthropic(
            api_key=settings.api_key.get_secret_value(),  # the one place the key is unwrapped
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
            http_client=http_client,  # None in real use; tests pass a fake transport
        )

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        extra = {"output_config": self._output_config} if self._output_config else {}
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                **extra,
            )
        except anthropic.APIError as exc:
            raise _to_model_error(exc) from exc
        u = response.usage
        input_total = (
            u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        )
        return ModelResponse(
            text="".join(block.text for block in response.content if block.type == "text"),
            stop_reason=_STOP_REASONS.get(response.stop_reason or "", "other"),
            usage=Usage(input_tokens=input_total, output_tokens=u.output_tokens),
            request_id=response._request_id,
        )


def _to_model_error(exc: anthropic.APIError) -> ModelError:
    request_id = getattr(exc, "request_id", None)  # only status errors carry one
    if isinstance(exc, anthropic.APITimeoutError):  # check before its parent class
        return ModelError("timeout", "the request timed out", request_id)
    if isinstance(exc, anthropic.APIConnectionError):
        return ModelError("provider_error", "could not reach the provider", request_id)
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ModelError("auth", "the API key was rejected", request_id)
    if isinstance(exc, anthropic.RateLimitError):
        return ModelError("rate_limited", "the provider is rate limiting this key", request_id)
    if isinstance(exc, anthropic.BadRequestError):
        return ModelError("bad_request", "the provider rejected the request", request_id)
    return ModelError("provider_error", "the provider returned an error", request_id)
