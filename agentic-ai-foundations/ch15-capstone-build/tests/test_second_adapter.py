"""The carrier question through Chapter 11's OpenAI-compatible adapter, over httpx.MockTransport.

The endpoint's replies are hand-written in the Chat Completions shape the adapter parses (the
same scripted turns as the fake model): no network and no key. It shows that the loop, the tools
and the checks run unchanged behind a second adapter, and that every tool result goes back
paired with its call's id.
"""

import json
from datetime import date
from pathlib import Path

import httpx
from ch15.model_client import ModelResponse
from ch15.openai_compatible_adapter import OpenAICompatibleAdapter
from ch15.research import run_research
from ch15.scripted import carriers
from ch15.settings import Settings
from ch15.tools import FixtureSearchBackend

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "search" / "carriers.json"
QUESTION = "Which carriers had the most late deliveries last quarter?"


def wire(response: ModelResponse) -> dict:
    calls = [
        {
            "id": c.id,
            "type": "function",
            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
        }
        for c in response.tool_calls
    ]
    message = {"role": "assistant", "content": response.text or None}
    if calls:
        message["tool_calls"] = calls
    usage = response.usage
    return {
        "choices": [
            {"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}
        ],
        "usage": {"prompt_tokens": usage.input_tokens, "completion_tokens": usage.output_tokens},
    }


def test_the_carrier_question_through_the_openai_compatible_adapter(exports: Path) -> None:
    replies = [wire(r) for r in carriers()]
    requests: list[dict] = []

    def endpoint(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=replies[len(requests) - 1])

    settings = Settings(exports_dir=exports)
    client = OpenAICompatibleAdapter(
        settings,
        base_url="https://llm.example.com/v1",
        api_key="test",
        model="any",
        transport=httpx.MockTransport(endpoint),
    )
    result = run_research(
        QUESTION, date(2026, 1, 15), settings, client, FixtureSearchBackend(FIXTURE)
    )
    assert result.outcome == "answered" and len(requests) == 3
    sent = requests[2]["messages"]  # the third request carries both search results
    asked = [c["id"] for m in sent if m["role"] == "assistant" for c in m.get("tool_calls", [])]
    answered = [m["tool_call_id"] for m in sent if m["role"] == "tool"]
    assert answered == asked  # every call has exactly one result, in order
