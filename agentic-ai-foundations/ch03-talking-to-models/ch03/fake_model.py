"""The fake model: scripted replies and errors, every call recorded, no network."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from ch03.model_client import Message, ModelError, ModelResponse, Usage


class ScriptExhausted(AssertionError):
    """The code under test made more model calls than the script allows."""


@dataclass
class FailMidStream:
    """stream() yields partial_text in chunks, then raises error; complete() just raises."""

    partial_text: str
    error: ModelError


ScriptItem = str | ModelResponse | ModelError | FailMidStream


class Call(BaseModel):
    system: str
    messages: list[Message]
    max_tokens: int


class FakeModelClient:
    def __init__(self, script: Sequence[ScriptItem], chunk_size: int = 12) -> None:
        self._script = list(script)
        self._chunk_size = chunk_size
        self.calls: list[Call] = []

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        item = self._next(system, messages, max_tokens)
        if isinstance(item, FailMidStream):
            raise item.error
        return item

    def stream(
        self, system: str, messages: Sequence[Message], max_tokens: int
    ) -> Iterator[str | ModelResponse]:
        item = self._next(system, messages, max_tokens)
        text = item.partial_text if isinstance(item, FailMidStream) else item.text
        for i in range(0, len(text), self._chunk_size):
            yield text[i : i + self._chunk_size]
        if isinstance(item, FailMidStream):
            raise item.error
        yield item

    def _next(
        self, system: str, messages: Sequence[Message], max_tokens: int
    ) -> ModelResponse | FailMidStream:
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
