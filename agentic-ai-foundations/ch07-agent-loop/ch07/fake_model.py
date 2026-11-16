"""Chapter 6's fake model: scripted responses, every request recorded.

New in Chapter 7: it accepts and records the per-call `timeout`, so tests can check that the
loop shrinks each call to the time left in the run.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from ch07.model_client import (
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
    timeout: float | None = None


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
