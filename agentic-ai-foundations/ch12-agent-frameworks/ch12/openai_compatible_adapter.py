"""A second ModelClient adapter: any OpenAI-compatible chat completions endpoint, over httpx.

New in Chapter 11. It speaks the same interface as the Anthropic adapter (complete() with a
per-call timeout, count_tokens()), so run_agent never knows which provider answered. The shapes
are Chapter 7's: stop reasons finished / tool_call / truncated / other, and Usage with input and
output tokens. Nothing in model_client.py changes.
"""

import json
from collections.abc import Sequence
from typing import Any

import httpx

from ch12.model_client import (
    Message,
    ModelError,
    ModelResponse,
    StopReason,
    ToolCall,
    ToolChoice,
    ToolDefinition,
    Usage,
    estimate_tokens,
)
from ch12.settings import Settings

_STOP_REASONS: dict[str, StopReason] = {
    "stop": "finished",
    "tool_calls": "tool_call",
    "length": "truncated",
}  # anything else becomes "other", which the loop reports as unexpected_stop

NOT_JSON = "arguments_not_json"  # an extra field, so the registry's strict models reject it
RETRY_STATUSES = {429, 500, 502, 503, 504}


# --- Outbound: our shapes to the wire ---


def to_wire_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,  # Chapter 6's pydantic-generated JSON Schema
        },
    }


def to_wire_tool_choice(choice: ToolChoice) -> str | dict[str, Any]:
    if choice.mode == "tool":
        if not choice.tool_name:
            raise ValueError('ToolChoice(mode="tool") needs a tool_name')
        return {"type": "function", "function": {"name": choice.tool_name}}
    return choice.mode  # "auto", "required" or "none"


def to_wire_messages(system: str, messages: Sequence[Message]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        if m.tool_results:  # one tool-role message per result, in order
            for r in m.tool_results:
                # The tool message has no error flag, so the flag travels in the text.
                content = f"ERROR: {r.content}" if r.is_error else r.content
                wire.append({"role": "tool", "tool_call_id": r.tool_call_id, "content": content})
            continue
        if not m.tool_calls:
            wire.append({"role": m.role, "content": m.content})
            continue
        wire.append(
            {
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in m.tool_calls
                ],
            }
        )
    return wire


# --- Inbound: the wire back to our shapes ---


def parse_arguments(raw: object) -> dict[str, Any]:
    """Arguments should be a JSON string. Never raise: a bad one becomes a field the registry
    rejects, so the model gets an error result it can act on and the call is not lost."""
    if isinstance(raw, dict):  # tolerated: some servers send an object, not a string
        return raw
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}  # a tool with no parameters
    try:
        value = json.loads(raw) if isinstance(raw, str) else None
    except json.JSONDecodeError:
        value = None
    return value if isinstance(value, dict) else {NOT_JSON: str(raw)}


def from_wire(body: dict[str, Any], request_id: str | None = None) -> ModelResponse:
    choice = body["choices"][0]
    message = choice["message"]
    calls = [
        ToolCall(
            id=c["id"],
            name=c["function"]["name"],
            arguments=parse_arguments(c["function"].get("arguments")),
        )
        for c in message.get("tool_calls") or []
    ]
    finish = choice.get("finish_reason") or ""
    # Trust the content over the label: calls under "stop" are still calls. Calls cut off
    # by the output limit stay "truncated", because their arguments are probably incomplete.
    stop = "tool_call" if calls and finish != "length" else _STOP_REASONS.get(finish, "other")
    usage = body.get("usage") or {}
    return ModelResponse(
        text=message.get("content") or "",
        stop_reason=stop,
        usage=Usage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        ),
        tool_calls=calls,
        request_id=request_id,
    )


def to_model_error(exc: httpx.HTTPError) -> ModelError:
    if isinstance(exc, httpx.TimeoutException):
        return ModelError("timeout", "the request timed out")
    if not isinstance(exc, httpx.HTTPStatusError):
        return ModelError("provider_error", "could not reach the endpoint")
    status, request_id = exc.response.status_code, exc.response.headers.get("x-request-id")
    if status in (401, 403):
        return ModelError("auth", "the API key was rejected", request_id)
    if status == 429:
        return ModelError("rate_limited", "the endpoint is rate limiting this key", request_id)
    if 400 <= status < 500:  # a wrong model name, an effort value the model rejects, ...
        detail = exc.response.text[:200]
        return ModelError("bad_request", f"the endpoint rejected the request: {detail}", request_id)
    return ModelError("provider_error", f"the endpoint returned HTTP {status}", request_id)


class OpenAICompatibleAdapter:
    provider_counts = False  # no count endpoint assumed: count_tokens is a local estimate

    def __init__(
        self,
        settings: Settings,
        *,
        base_url: str,
        api_key: str,
        model: str,
        reasoning_effort: str | None = None,
        max_tokens_param: str = "max_tokens",
        transport: httpx.BaseTransport | None = None,  # httpx.MockTransport in tests
    ) -> None:
        self._settings = settings
        self._model = model
        self._effort = reasoning_effort
        self._max_tokens_param = max_tokens_param
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=settings.timeout_seconds,  # client-wide, like the SDK adapter
            transport=transport,
        )

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        tools: Sequence[ToolDefinition] = (),
        tool_choice: ToolChoice | None = None,
        timeout: float | None = None,
    ) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": to_wire_messages(system, messages),
            self._max_tokens_param: max_tokens,  # the spelling comes from configuration
        }
        if tools:
            body["tools"] = [to_wire_tool(t) for t in tools]
            if tool_choice is not None:  # otherwise the endpoint's default applies
                body["tool_choice"] = to_wire_tool_choice(tool_choice)
                if not tool_choice.allow_parallel:
                    body["parallel_tool_calls"] = False
        if self._effort:
            body["reasoning_effort"] = self._effort  # omitted entirely when not configured
        response = self._post(body, timeout)
        try:
            return from_wire(response.json(), response.headers.get("x-request-id"))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            # A 200 whose body is not the expected shape: retrying will not change it.
            raise ModelError("provider_error", f"unreadable response: {exc!r}") from exc

    def _post(self, body: dict[str, Any], timeout: float | None) -> httpx.Response:
        """Like the SDK adapter: up to MAX_RETRIES extra attempts on rate limits, server errors
        and connection failures, each with the same timeout. Retries are immediate here."""
        extra = {"timeout": timeout} if timeout is not None else {}
        for attempt in range(1 + self._settings.max_retries):
            last = attempt == self._settings.max_retries
            try:
                response = self._http.post("/chat/completions", json=body, **extra)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                if last or exc.response.status_code not in RETRY_STATUSES:
                    raise to_model_error(exc) from exc
            except httpx.TransportError as exc:  # timeouts and connection failures
                if last:
                    raise to_model_error(exc) from exc
        raise AssertionError("unreachable")

    def count_tokens(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] = (),
        timeout: float | None = None,
    ) -> int:
        return estimate_tokens(system, messages, tools, self._settings.chars_per_token)
