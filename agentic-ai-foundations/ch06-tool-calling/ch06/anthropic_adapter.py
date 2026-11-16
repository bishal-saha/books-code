"""Chapter 3's Anthropic adapter (complete() only), extended for tool calling.

Still the only file that imports the SDK. New in Chapter 6: tool definitions and tool choice
go out in the request, tool_use blocks come back as ToolCall objects, and messages that carry
tool calls or tool results are rebuilt as the provider's content blocks.
"""

from collections.abc import Sequence

import anthropic
from anthropic.types import MessageParam, ToolChoiceParam, ToolParam

from ch06.model_client import (
    Message,
    ModelError,
    ModelResponse,
    StopReason,
    ToolCall,
    ToolChoice,
    ToolDefinition,
    Usage,
)
from ch06.settings import Settings

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "finished",
    "stop_sequence": "finished",
    "max_tokens": "truncated",
    "model_context_window_exceeded": "truncated",
    "tool_use": "tool_call",
}  # anything else, "refusal" included, becomes "other"


def to_sdk_tool(tool: ToolDefinition) -> ToolParam:
    return {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}


def to_sdk_tool_choice(choice: ToolChoice) -> ToolChoiceParam:
    if choice.mode == "none":
        return {"type": "none"}  # this type has no disable_parallel_tool_use field
    if choice.mode == "tool":
        if not choice.tool_name:
            raise ValueError('ToolChoice(mode="tool") needs a tool_name')
        sdk: ToolChoiceParam = {"type": "tool", "name": choice.tool_name}
    elif choice.mode == "required":
        sdk = {"type": "any"}
    else:
        sdk = {"type": "auto"}
    if not choice.allow_parallel:
        sdk["disable_parallel_tool_use"] = True  # inside tool_choice, never top level
    return sdk


def to_sdk_message(m: Message) -> MessageParam:
    if m.tool_results:  # the program's reply: one tool_result block per call, nothing else
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": r.tool_call_id,
                    "content": r.content,
                    "is_error": r.is_error,
                }
                for r in m.tool_results
            ],
        }
    if not m.tool_calls:
        return {"role": m.role, "content": m.content}  # exactly Chapter 3's shape
    blocks: list = [{"type": "text", "text": m.content}] if m.content else []
    blocks += [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls
    ]
    return {"role": "assistant", "content": blocks}


class AnthropicAdapter:
    def __init__(
        self, settings: Settings, http_client: anthropic.DefaultHttpxClient | None = None
    ) -> None:
        assert settings.api_key is not None
        self._model = settings.model
        self._client = anthropic.Anthropic(
            api_key=settings.api_key.get_secret_value(),  # the one place the key is unwrapped
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
            http_client=http_client,  # None in real use; tests pass a fake transport
        )

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        tools: Sequence[ToolDefinition] = (),
        tool_choice: ToolChoice | None = None,
    ) -> ModelResponse:
        extra = {}
        if tools:  # without tools the request is exactly Chapter 3's
            extra["tools"] = [to_sdk_tool(t) for t in tools]
            extra["tool_choice"] = to_sdk_tool_choice(tool_choice or ToolChoice())
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[to_sdk_message(m) for m in messages],
                **extra,
            )
        except anthropic.APIError as exc:
            raise _to_model_error(exc) from exc
        u = response.usage
        input_total = (
            u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        )
        return ModelResponse(
            text="".join(b.text for b in response.content if b.type == "text"),
            stop_reason=_STOP_REASONS.get(response.stop_reason or "", "other"),
            usage=Usage(input_tokens=input_total, output_tokens=u.output_tokens),
            tool_calls=[
                ToolCall(id=b.id, name=b.name, arguments=dict(b.input))
                for b in response.content
                if b.type == "tool_use"
            ],
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
    if isinstance(exc, anthropic.BadRequestError):  # e.g. a tool choice the model rejects
        return ModelError(
            "bad_request", f"the provider rejected the request: {exc.message}", request_id
        )
    return ModelError("provider_error", "the provider returned an error", request_id)
