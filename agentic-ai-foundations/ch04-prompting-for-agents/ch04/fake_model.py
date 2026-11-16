"""The fake model from Chapter 3: scripted replies, every call recorded, no network."""

from collections.abc import Sequence

from pydantic import BaseModel

from ch04.model_client import Message, ModelResponse, Usage


class Call(BaseModel):
    system: str
    messages: list[Message]
    max_tokens: int


class FakeModelClient:
    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.calls: list[Call] = []

    def complete(self, system: str, messages: Sequence[Message], max_tokens: int) -> ModelResponse:
        self.calls.append(Call(system=system, messages=list(messages), max_tokens=max_tokens))
        if not self._replies:
            raise AssertionError("FakeModelClient ran out of scripted replies")
        text = self._replies.pop(0)
        return ModelResponse(
            text=text,
            stop_reason="finished",
            usage=Usage(input_tokens=len(system.split()), output_tokens=len(text.split())),
        )
