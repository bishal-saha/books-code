"""One round trip on the fake model: id pairing, one message for parallel results, stops."""

import httpx
import pytest
from ch06.fake_model import FakeModelClient
from ch06.model_client import ModelResponse, ToolCall, ToolChoice, Usage
from ch06.prompts import load_prompt
from ch06.round_trip import run_round_trip
from ch06.scripted import SCENARIOS
from ch06.tools import build_registry

SYSTEM = load_prompt("order_lookup", 1).body
USAGE = Usage(input_tokens=0, output_tokens=0)


@pytest.fixture
def registry(kestrel_url):
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        yield build_registry(http)


def tool_response(*calls: ToolCall) -> ModelResponse:
    return ModelResponse(text="", stop_reason="tool_call", usage=USAGE, tool_calls=list(calls))


def test_prompt_has_the_six_sections_in_order():
    headings = [line for line in SYSTEM.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Role",
        "## Task",
        "## Constraints",
        "## Data",
        "## Output format",
        "## When you don't know",
    ]
    assert "NEEDS INFO" in SYSTEM


def test_single_call_result_carries_the_call_id(registry):
    question, fake = SCENARIOS["single"]()
    final = run_round_trip(fake, registry, SYSTEM, question, 400, out=lambda s: None)
    assert final.stop_reason == "finished"
    sent = fake.calls[1].messages
    assert [m.role for m in sent] == ["user", "assistant", "user"]
    assert sent[1].tool_calls[0].id == "toolu_fake_01"
    assert sent[2].tool_results[0].tool_call_id == "toolu_fake_01"
    assert '"status": "shipped"' in sent[2].tool_results[0].content


def test_parallel_calls_get_one_result_each_in_one_message(registry):
    question, fake = SCENARIOS["parallel"]()
    run_round_trip(fake, registry, SYSTEM, question, 400, out=lambda s: None)
    last = fake.calls[1].messages[-1]
    assert last.role == "user"
    ids = [r.tool_call_id for r in last.tool_results]
    assert ids == ["toolu_fake_01", "toolu_fake_02", "toolu_fake_03", "toolu_fake_04"]
    assert len(fake.calls[1].messages) == 3  # not one message per result


def test_an_error_result_still_answers_its_call(registry):
    fake = FakeModelClient(
        [
            tool_response(
                ToolCall(id="a", name="get_shipment", arguments={"order_id": "O-0017612"}),
                ToolCall(id="b", name="get_order", arguments={"order_id": "O-42"}),
            ),
            "NEEDS INFO: O-0017612 has not shipped; O-42 is not a valid order ID.",
        ]
    )
    run_round_trip(fake, registry, SYSTEM, "q", 400, out=lambda s: None)
    results = fake.calls[1].messages[-1].tool_results
    assert [(r.tool_call_id, r.is_error) for r in results] == [("a", True), ("b", True)]


def test_truncated_response_raises_before_any_dispatch(registry):
    cut = ModelResponse(
        text="",
        stop_reason="truncated",
        usage=USAGE,
        tool_calls=[ToolCall(id="x", name="get_order", arguments={})],
    )
    fake = FakeModelClient([cut])
    with pytest.raises(RuntimeError, match="cut off"):
        run_round_trip(fake, registry, SYSTEM, "q", 400, out=lambda s: None)
    assert len(fake.calls) == 1


def test_a_second_tool_request_stops_without_a_third_call(registry):
    get = ToolCall(id="c1", name="get_order", arguments={"order_id": "O-0000141"})
    ship = ToolCall(id="c2", name="get_shipment", arguments={"order_id": "O-0000141"})
    fake = FakeModelClient([tool_response(get), tool_response(ship)])
    lines: list[str] = []
    final = run_round_trip(fake, registry, SYSTEM, "q", 400, out=lines.append)
    assert final.stop_reason == "tool_call"
    assert len(fake.calls) == 2
    assert "agent loop" in lines[-1]


def test_tool_choices_reach_each_model_call(registry):
    forced = ToolChoice(mode="tool", tool_name="get_order")
    forbid = ToolChoice(mode="none")
    question, fake = SCENARIOS["single"]()
    run_round_trip(fake, registry, SYSTEM, question, 400, forced, forbid, out=lambda s: None)
    assert fake.calls[0].tool_choice == forced
    assert fake.calls[1].tool_choice == forbid
