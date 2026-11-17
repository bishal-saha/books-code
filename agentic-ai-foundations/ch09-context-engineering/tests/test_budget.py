"""BudgetTracker on its own: remaining room and the pre-step check."""

from ch09.budget import BudgetTracker, RunBudget, StopCause

BUDGET = RunBudget(max_steps=3, max_total_tokens=1_000, max_wall_seconds=10.0)


def test_remaining_room_never_goes_negative():
    now = [100.0]
    tracker = BudgetTracker(BUDGET, clock=lambda: now[0])
    tracker.record(input_tokens=900, output_tokens=300)
    now[0] = 112.0
    assert (tracker.total_tokens, tracker.remaining_tokens()) == (1_200, 0)
    assert (tracker.elapsed(), tracker.remaining_seconds()) == (12.0, 0.0)


def test_check_names_the_limit():
    now = [0.0]
    tracker = BudgetTracker(BUDGET, clock=lambda: now[0])
    assert tracker.check(min_tokens=256, min_seconds=1.0) is None
    tracker.record(700, 100)  # 200 tokens left: not enough for a useful call
    assert tracker.check(min_tokens=256, min_seconds=1.0) is StopCause.TOKEN_LIMIT
    tracker = BudgetTracker(BUDGET, clock=lambda: now[0])
    now[0] = 9.5
    assert tracker.check(min_tokens=256, min_seconds=1.0) is StopCause.TIME_LIMIT
