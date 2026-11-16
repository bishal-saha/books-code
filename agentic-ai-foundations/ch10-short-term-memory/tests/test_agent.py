"""The loop with a context policy: Maya's session against the mock API, and the new exits."""

import httpx
import pytest
from ch10.agent import run_agent
from ch10.budget import StopCause
from ch10.demo import DEMO_POLICIES, SUMMARY_AT
from ch10.fake_model import FakeModelClient
from ch10.histories import maya_history
from ch10.model_client import ModelError
from ch10.scripted import FAKE_BUDGET, FAKE_LIMITS, FOLLOW_UPS, TASK, maya_client
from ch10.state import ConversationState, check_pairing
from ch10.tools import build_registry


@pytest.fixture
def registry(kestrel_url):
    with httpx.Client(base_url=kestrel_url, timeout=10.0) as http:
        yield build_registry(http)


def run_session(strategy: str, registry):
    client = maya_client(SUMMARY_AT if strategy == "compact" else None)
    state, results = ConversationState.start(TASK), []
    for question in [None, *FOLLOW_UPS]:
        if question is not None:
            state.add_user(question)
        result = run_agent(
            client, "system", state, registry, FAKE_BUDGET, FAKE_LIMITS, DEMO_POLICIES[strategy]
        )
        results.append(result)
        state = result.state
    return results, client


def test_the_session_compacts_once_in_the_last_turn(registry):
    results, client = run_session("compact", registry)
    assert [r.cause for r in results] == [StopCause.FINISHED] * 4
    events = [(n, s.index, s.context) for n, r in enumerate(results) for s in r.steps if s.context]
    assert [(n, i, e.outcome) for n, i, e in events] == [(3, 1, "compacted")]
    final = results[-1].state
    assert final.compactions == 1 and "O-0006066" in final.summary
    assert check_pairing(final) == []
    assert client.calls[-1].messages[0].content.startswith(TASK)  # the task is still pinned


def test_the_trim_session_drops_the_oldest_units(registry):
    results, _ = run_session("trim", registry)
    trims = [s.context for r in results for s in r.steps if s.context]
    assert [(t.kind, t.units_dropped) for t in trims] == [("trim", 5)]
    assert check_pairing(results[-1].state) == []


def test_run_agent_never_changes_the_state_it_was_given(registry):
    state = ConversationState.start(TASK)
    run_agent(
        maya_client(), "system", state, registry, FAKE_BUDGET, FAKE_LIMITS, DEMO_POLICIES["trim"]
    )
    assert state.messages == []


def test_a_malformed_state_is_refused_before_any_model_call(registry):
    state = maya_history()
    del state.messages[1]  # drop the results of the first tool round
    client = FakeModelClient([])
    with pytest.raises(ValueError, match="message 0: tool calls with no results message"):
        run_agent(client, "s", state, registry, FAKE_BUDGET, FAKE_LIMITS, DEMO_POLICIES["trim"])
    assert client.calls == [] and client.count_calls == 0


class CountFails(FakeModelClient):
    def count_tokens(self, *args, **kwargs):
        raise ModelError("provider_error", "count endpoint unavailable")


def test_a_failed_token_count_ends_the_run_with_model_error(registry):
    result = run_agent(
        CountFails([]), "s", maya_history(), registry, FAKE_BUDGET, FAKE_LIMITS,
        DEMO_POLICIES["trim"],
    )  # fmt: skip
    assert result.cause == StopCause.MODEL_ERROR and result.steps == []
