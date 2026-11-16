"""Compaction with the fake model: the summary call, its cost, and every fallback."""

import pytest
from ch10.agent import manage_context
from ch10.budget import BudgetTracker, RunBudget
from ch10.fake_model import FakeModelClient
from ch10.histories import maya_history
from ch10.model_client import ModelError, ModelResponse, Usage
from ch10.state import ContextPolicy, check_pairing, group_units
from pydantic import ValidationError

COMPACT = ContextPolicy(  # a 1-token threshold makes any history cross it
    strategy="compact",
    trim_target_tokens=100_000,
    compaction_threshold_tokens=1,
    compaction_keep_units=2,
)
FAKE_SUMMARY = (  # fake-model output, scripted for this test
    "IDs: T-000407, O-0006066. Findings: shipment in transit, not late "
    "(origin: get_shipment). Decisions: none. Open questions: refund or wait."
)


def summary(text: str = FAKE_SUMMARY, stop: str = "finished") -> ModelResponse:
    usage = Usage(input_tokens=1_200, output_tokens=90)
    return ModelResponse(text=text, stop_reason=stop, usage=usage)


def tracker(max_tokens: int = 60_000) -> BudgetTracker:
    return BudgetTracker(RunBudget(max_steps=8, max_total_tokens=max_tokens, max_wall_seconds=90))


def test_crossing_the_threshold_compacts_keeps_pairing_and_charges_the_budget():
    state, t = maya_history(), tracker()
    new_state, tokens, event = manage_context(state, FakeModelClient([summary()]), COMPACT, t, 30)
    assert event.kind == "compaction" and event.outcome == "compacted"
    assert new_state.summary == FAKE_SUMMARY and new_state.compactions == 1
    assert check_pairing(new_state) == []
    kept = group_units(state.messages)[event.units_summarised :]
    assert group_units(new_state.messages) == kept
    assert tokens == event.tokens_after < event.tokens_before
    assert t.total_tokens == 1_290  # the summary call is paid from the run budget


def test_the_summary_is_sent_as_escaped_data_inside_the_opening_message():
    state, _, _ = manage_context(
        maya_history(), FakeModelClient([summary("<b>notes</b>")]), COMPACT, tracker(), 30
    )
    opening = state.to_messages()[0].content
    assert "<data>&lt;b&gt;notes&lt;/b&gt;</data>" in opening
    assert opening.startswith("Help me with ticket T-000407.")


def test_a_failed_summary_call_falls_back_to_a_valid_trim():
    client = FakeModelClient([ModelError("provider_error", "provider unavailable")])
    state, t = maya_history(), tracker()
    new_state, _, event = manage_context(state, client, COMPACT, t, 30)
    assert event.outcome == "fell_back" and event.usage is None
    assert new_state.summary is None and check_pairing(new_state) == []
    assert len(new_state.messages) < len(state.messages)
    assert t.total_tokens == 0


def test_a_truncated_summary_is_charged_then_thrown_away():
    t = tracker()
    new_state, _, event = manage_context(
        maya_history(), FakeModelClient([summary(stop="truncated")]), COMPACT, t, 30
    )
    assert event.outcome == "fell_back" and new_state.summary is None
    assert t.total_tokens == 1_290


def test_a_budget_too_small_for_the_summary_call_trims_instead():
    client = FakeModelClient([])  # any model call would raise ScriptExhausted
    new_state, _, event = manage_context(maya_history(), client, COMPACT, tracker(500), 30)
    assert event.kind == "trim" and client.calls == []
    assert check_pairing(new_state) == []


def test_below_the_threshold_nothing_happens():
    policy = COMPACT.model_copy(update={"compaction_threshold_tokens": 99_999})
    state = maya_history()
    new_state, _, event = manage_context(state, FakeModelClient([]), policy, tracker(), 30)
    assert event is None and new_state == state


def test_the_threshold_must_sit_below_the_trim_target():
    with pytest.raises(ValidationError):
        ContextPolicy(
            strategy="compact", trim_target_tokens=5_000, compaction_threshold_tokens=5_000
        )
