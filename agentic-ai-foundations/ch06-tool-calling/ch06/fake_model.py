"""Chapter 3's fake model, extended for tools: scripted responses, every request recorded.

Scripted responses can carry tool calls, so tests (and `round_trip --fake`) run the whole
call/result cycle without a key or a network connection to a provider.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from ch06.model_client import (
    Message,
    ModelError,
    ModelResponse,
    ToolChoice,
    ToolDefinition,
    Usage,
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


class FakeModelClient:
    def __init__(self, script: Sequence[ScriptItem]) -> None:
        self._script = list(script)
        self.calls: list[Call] = []

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        tools: Sequence[ToolDefinition] = (),
        tool_choice: ToolChoice | None = None,
    ) -> ModelResponse:
        self.calls.append(
            Call(
                system=system,
                messages=list(messages),
                max_tokens=max_tokens,
                tools=list(tools),
                tool_choice=tool_choice,
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
