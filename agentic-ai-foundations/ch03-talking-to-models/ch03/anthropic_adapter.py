"""The Anthropic adapter: the one library file that imports the SDK."""

from collections.abc import Iterator, Sequence

import anthropic
import httpx2  # the SDK's HTTP library, needed for errors raised mid-stream

from ch03.model_client import Message, ModelError, ModelResponse, StopReason, Usage
from ch03.settings import Settings

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "finished",
    "stop_sequence": "finished",
    "max_tokens": "truncated",
    "model_context_window_exceeded": "truncated",
    "tool_use": "tool_call",
}
CONNECT_TIMEOUT_S = 5.0  # the SDK's own connect default; an unreachable host fails fast


class AnthropicAdapter:
    def __init__(
        self, settings: Settings, http_client: anthropic.DefaultHttpxClient | None = None
    ) -> None:
        assert settings.api_key is not None
        self._model = settings.model
        self._client = anthropic.Anthropic(
            api_key=settings.api_key.get_secret_value(),  # the one place the key is unwrapped
            timeout=anthropic.Timeout(settings.timeout_seconds, connect=CONNECT_TIMEOUT_S),
            max_retries=settings.max_retries,
            http_client=http_client,  # None in real use; tests pass a fake transport
        )
        # Thinking tokens count against max_tokens, and the neutral types carry no
        # thinking blocks, so thinking is off unless MODEL_THINKING=adaptive.
        self._thinking: dict = (
            {"thinking": {"type": "disabled"}} if settings.thinking == "off" else {}
        )

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=_to_sdk_messages(messages),
                **self._thinking,
            )
        except anthropic.APIError as exc:
            raise _to_model_error(exc) from exc
        return _to_model_response(response, response._request_id)

    def stream(
        self, system: str, messages: Sequence[Message], max_tokens: int
    ) -> Iterator[str | ModelResponse]:
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=_to_sdk_messages(messages),
                **self._thinking,
            ) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
                request_id = stream.request_id
        except anthropic.APIError as exc:
            raise _to_model_error(exc) from exc
        except httpx2.TimeoutException as exc:  # a stall while the body is read
            raise ModelError("timeout", "the stream stalled") from exc
        except httpx2.TransportError as exc:  # the connection dropped partway
            raise ModelError("provider_error", "the stream was interrupted") from exc
        yield _to_model_response(final, request_id)


def _to_sdk_messages(messages: Sequence[Message]) -> list[anthropic.types.MessageParam]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _to_model_response(response: anthropic.types.Message, request_id: str | None) -> ModelResponse:
    u = response.usage
    input_total = (
        u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
    )
    return ModelResponse(
        # Join every text block; skip block types this chapter doesn't handle yet.
        text="".join(block.text for block in response.content if block.type == "text"),
        stop_reason=_STOP_REASONS.get(response.stop_reason or "", "other"),
        usage=Usage(input_tokens=input_total, output_tokens=u.output_tokens),
        request_id=request_id,
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
    if isinstance(exc, (anthropic.BadRequestError, anthropic.NotFoundError)):  # 404: unknown MODEL
        return ModelError("bad_request", "the provider rejected the request", request_id)
    return ModelError("provider_error", "the provider returned an error", request_id)
