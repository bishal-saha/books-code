"""The loop's new paths: the one retry, the rejected answer, the time check and compaction."""

from datetime import date
from pathlib import Path

from ch15.agent import run_agent
from ch15.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch15.citations import citable_locations
from ch15.fake_model import FakeModelClient
from ch15.final import check_final, retry_message
from ch15.prompts import build_system_prompt
from ch15.scripted import LATE_Q4, carriers, invented_url_corrected, invented_url_rejected
from ch15.settings import Settings
from ch15.state import ConversationState, check_pairing
from ch15.tools import FixtureSearchBackend, build_registry

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "search" / "carriers.json"
QUESTION = "Which carriers had the most late deliveries last quarter?"


class ManualClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SlowSearch(FixtureSearchBackend):
    """The fixture backend, but every search takes 40 seconds of the clock."""

    def __init__(self, clock: ManualClock) -> None:
        super().__init__(FIXTURE)
        self.clock = clock

    def search(self, query: str, max_results: int, timeout_s: float):
        self.clock.now += 40.0
        return super().search(query, max_results, timeout_s)


def run(script, exports, settings=None, budget=None, clock=None, backend=None):
    settings = settings or Settings(exports_dir=exports)
    backend = backend or FixtureSearchBackend(FIXTURE)
    max_chars = settings.tool_result_max_chars
    registry = build_registry(exports, backend, lambda: 3.0, max_chars, citable_locations)
    budget = budget or RunBudget(8, 60_000, 120.0)
    tracker = BudgetTracker(budget, clock=clock) if clock else None
    client = FakeModelClient(script)
    result = run_agent(
        client,
        build_system_prompt(date(2026, 1, 15)),
        ConversationState.start(QUESTION),
        registry,
        budget,
        CallLimits(1024, 30.0),
        settings.context_policy(),
        check=lambda text: check_final(text, registry.citable),
        retry=lambda check: retry_message(check, registry.citable),
        tracker=tracker,
    )
    return result, registry, client


def test_an_accepted_answer_ends_the_run(exports: Path) -> None:
    result, _, _ = run(carriers(), exports)
    assert result.cause is StopCause.FINISHED and result.answer is not None
    assert (len(result.steps), result.answer_retries) == (3, 0)


def test_one_retry_fixes_an_unreturned_url(exports: Path) -> None:
    result, _, client = run(invented_url_corrected(), exports)
    assert result.cause is StopCause.FINISHED and result.answer is not None
    assert (len(result.steps), result.answer_retries) == (4, 1)  # the retry is a step
    retry = client.calls[3].messages[-1].content
    assert "harbour-express-complaints" in retry and "shipments.csv" in retry
    assert result.steps[2].answer_errors and not result.steps[3].answer_errors


def test_a_second_failure_is_finished_with_no_answer(exports: Path) -> None:
    result, _, _ = run(invented_url_rejected(), exports)
    assert result.cause is StopCause.FINISHED  # the model did end its turn
    assert result.answer is None and result.answer_retries == 1
    assert result.answer_errors == [result.steps[3].answer_errors[0]]
    assert "harbour-express-complaints" in result.final_text  # kept for the trace


def test_the_retry_needs_a_step_of_its_own(exports: Path) -> None:
    result, _, _ = run(invented_url_corrected(), exports, budget=RunBudget(3, 60_000, 120.0))
    assert result.cause is StopCause.STEP_LIMIT and result.answer is None


def test_time_is_checked_right_after_tool_calls(exports: Path) -> None:
    clock = ManualClock()
    budget = RunBudget(8, 60_000, 60.0)
    result, _, _ = run(carriers(), exports, budget=budget, clock=clock, backend=SlowSearch(clock))
    assert result.cause is StopCause.TIME_LIMIT  # two 40 s searches in step 2
    assert len(result.steps) == 2 and clock.now == 80.0


def test_forced_compaction_keeps_pairs_and_the_citable_set(exports: Path) -> None:
    settings = Settings(
        exports_dir=exports, compaction_threshold_tokens=300, compaction_keep_units=1
    )
    script = carriers()
    # The summary call consumes a scripted reply, placed where compaction fires (before step 3).
    summary = "IDs: none. Findings: late counts per carrier (origin shipments.csv); reviews."
    script.insert(2, summary)
    result, registry, _ = run(script, exports, settings)
    assert result.answer is not None and result.state.compactions == 1
    assert check_pairing(result.state) == []
    assert registry.citable >= {"shipments.csv", "https://reviews.example.com/harbour-express"}
    assert result.steps[2].context is not None and result.steps[2].context.kind == "compaction"


def test_count_rows_arguments_in_the_script_are_valid() -> None:
    from ch15.tools import CountRowsArgs

    CountRowsArgs(**LATE_Q4)
