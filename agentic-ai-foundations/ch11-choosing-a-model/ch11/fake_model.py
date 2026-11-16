"""Chapter 7's fake model: scripted responses, every request recorded.

New in Chapter 9: count_tokens() returns a deterministic local estimate (provider_counts is
False), and every count request is recorded, so tests can check how often the inspector counts.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from ch11.model_client import (
    Message,
    ModelError,
    ModelResponse,
    ToolChoice,
    ToolDefinition,
    Usage,
    estimate_tokens,
)


class ScriptExhausted(AssertionError):
    """The code under test made more model calls than the script allows."""


ScriptItem = str | ModelResponse | ModelError


class Call(BaseModel):
    system: str
    messages: list[Message]  # a copy: the caller keeps appending to its own list
    max_tokens: int
    tools: list[ToolDefinition]
    tool_choice: ToolChoice | None
    timeout: float | None = None


class FakeModelClient:
    provider_counts = False  # count_tokens is a local estimate, never a provider count

    def __init__(self, script: Sequence[ScriptItem], chars_per_token: float = 4.0) -> None:
        self._script = list(script)
        self.calls: list[Call] = []
        self.count_calls = 0
        self.chars_per_token = chars_per_token

    def count_tokens(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] = (),
        timeout: float | None = None,
    ) -> int:
        self.count_calls += 1
        return estimate_tokens(system, messages, tools, self.chars_per_token)

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        tools: Sequence[ToolDefinition] = (),
        tool_choice: ToolChoice | None = None,
        timeout: float | None = None,
    ) -> ModelResponse:
        self.calls.append(
            Call(
                system=system,
                messages=list(messages),
                max_tokens=max_tokens,
                tools=list(tools),
                tool_choice=tool_choice,
                timeout=timeout,
            )
        )
        if not self._script:
            raise ScriptExhausted(f"the script ran out at call {len(self.calls)}")
        item = self._script.pop(0)
        if isinstance(item, ModelError):
            raise item
        if isinstance(item, str):  # shorthand: a finished reply, word counts as usage
            usage = Usage(input_tokens=len(system.split()), output_tokens=len(item.split()))
            return ModelResponse(text=item, stop_reason="finished", usage=usage)
        return item
