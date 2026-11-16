"""Chapter 3's fake model, trimmed to complete(): scripted replies, every call recorded."""

from collections.abc import Sequence

from pydantic import BaseModel

from ch05.model_client import Message, ModelError, ModelResponse, Usage


class ScriptExhausted(AssertionError):
    """The code under test made more model calls than the script allows."""


ScriptItem = str | ModelResponse | ModelError


class Call(BaseModel):
    system: str
    messages: list[Message]
    max_tokens: int


class FakeModelClient:
    def __init__(self, script: Sequence[ScriptItem]) -> None:
        self._script = list(script)
        self.calls: list[Call] = []

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        self.calls.append(Call(system=system, messages=list(messages), max_tokens=max_tokens))
        if not self._script:
            raise ScriptExhausted(f"the script ran out at call {len(self.calls)}")
        item = self._script.pop(0)
        if isinstance(item, ModelError):
            raise item
        if isinstance(item, str):  # shorthand: a finished reply with word counts as usage
            words = len(system.split()) + sum(len(m.content.split()) for m in messages)
            usage = Usage(input_tokens=words, output_tokens=len(item.split()))
            return ModelResponse(text=item, stop_reason="finished", usage=usage)
        return item
