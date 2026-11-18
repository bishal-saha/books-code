"""The adapter's request: thinking is disabled unless MODEL_THINKING=adaptive. No network."""

from types import SimpleNamespace

import pytest
from ch04.anthropic_adapter import AnthropicAdapter
from ch04.model_client import Message
from ch04.settings import Settings


class RecordingMessages:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(
            input_tokens=10, output_tokens=2, cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
        )  # fmt: skip
        text = SimpleNamespace(type="text", text="Hi.")
        return SimpleNamespace(content=[text], stop_reason="end_turn", usage=usage)


@pytest.mark.parametrize(
    ("thinking", "expected"), [("off", {"type": "disabled"}), ("adaptive", None)]
)
def test_thinking_setting_reaches_the_request(thinking, expected):
    settings = Settings(model="test-model", api_key="sk-test", thinking=thinking)
    adapter = AnthropicAdapter(settings)
    recorder = RecordingMessages()
    adapter._client = SimpleNamespace(messages=recorder)

    response = adapter.complete("system", [Message(role="user", content="hello")], max_tokens=50)

    assert recorder.kwargs.get("thinking") == expected
    assert (response.text, response.stop_reason) == ("Hi.", "finished")
