"""check_pairing itself, then trimming: no kept tool round ever loses half of itself."""

import pytest
from ch10.fake_model import FakeModelClient
from ch10.histories import maya_history, with_messages
from ch10.model_client import Message, ToolCall, ToolResult
from ch10.state import check_pairing, cut_points, group_units, history_tokens, trim_to_target


def call(*ids: str) -> Message:
    return Message(
        role="assistant", tool_calls=[ToolCall(id=i, name="get_order", arguments={}) for i in ids]
    )


def results(*ids: str, text: str = "") -> Message:
    return Message(
        role="user",
        content=text,
        tool_results=[ToolResult(tool_call_id=i, content="{}") for i in ids],
    )


@pytest.mark.parametrize(
    "messages, expected",
    [
        ([results("a")], ["message 0: tool result a has no call"]),
        ([call("a", "b"), results("a")], ["message 0: tool call b has no result"]),
        ([call("a")], ["message 0: tool calls with no results message after them"]),
        ([call("a"), results("a", "z")], ["message 1: tool result z has no call"]),
        ([call("a"), results("a", text="Thanks")], ["message 1: text in a tool-results message"]),
    ],
)
def test_check_pairing_reports_each_violation(messages, expected):
    assert check_pairing(with_messages(messages)) == expected


def test_a_valid_history_has_no_violations():
    assert check_pairing(maya_history()) == []


def test_trim_drops_whole_units_from_a_cut_point():
    state, client = maya_history(), FakeModelClient([])
    target = history_tokens(state, client, None) // 2
    trimmed, report = trim_to_target(state, client, target)
    original = group_units(state.messages)
    assert report.units_dropped in cut_points(original)
    assert group_units(trimmed.messages) == original[report.units_dropped :]
    assert trimmed.task == state.task and check_pairing(trimmed) == []


def test_every_kept_tool_round_is_whole_at_every_target():
    state, client = maya_history(), FakeModelClient([])
    full = history_tokens(state, client, None)
    for target in range(0, full, max(full // 10, 1)):
        trimmed, _ = trim_to_target(state, client, target)
        for unit in group_units(trimmed.messages):
            if unit.kind == "tool_round":
                assert {c.id for c in unit.tool_calls} == {
                    r.tool_call_id for r in unit.tool_results
                }


def test_an_oversized_newest_turn_is_kept_whole_and_flagged():
    state = maya_history(shipment_rows=400)
    trimmed, report = trim_to_target(state, FakeModelClient([]), target_tokens=1)
    assert report.over_target
    assert check_pairing(trimmed) == []
    assert [u.kind for u in group_units(trimmed.messages)] == ["question", "tool_round"]


def test_the_rendered_history_never_has_two_user_messages_in_a_row():
    trimmed, _ = trim_to_target(maya_history(), FakeModelClient([]), target_tokens=1)
    roles = [m.role for m in trimmed.to_messages()]
    assert roles[0] == "user"
    assert all(a != b for a, b in zip(roles, roles[1:], strict=False))


def test_trimming_never_changes_its_input():
    state = maya_history()
    before = state.model_dump()
    trim_to_target(state, FakeModelClient([]), target_tokens=1)
    assert state.model_dump() == before
