"""Transient or permanent, and the bounded retry helper. No sleeps: a fake clock moves by hand."""

import random

import httpx
import pytest
from ch16.failures import FailureKind, SearchHTTPError, classify
from ch16.model_client import ModelError
from ch16.registry import ToolError
from ch16.retry import RetryPolicy, backoff_s, retry_call
from ch16.sandbox import SandboxError

T, P = FailureKind.TRANSIENT, FailureKind.PERMANENT


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (ModelError("timeout", "the request timed out"), T),
        (ModelError("rate_limited", "429"), T),
        (ModelError("provider_error", "529 overloaded"), T),
        (ModelError("auth", "the API key was rejected"), P),
        (ModelError("bad_request", "400"), P),
        (SearchHTTPError(503), T),
        (SearchHTTPError(429), T),
        (SearchHTTPError(408), T),
        (SearchHTTPError(401), P),
        (SearchHTTPError(404), P),
        (httpx.ReadTimeout("stalled"), T),
        (httpx.ConnectError("refused"), T),
        (httpx.ReadError("connection reset mid-response"), T),
        (httpx.RemoteProtocolError("bad framing"), T),
        (SandboxError("outside the sandboxed folder"), P),
        (ToolError("Division by zero."), P),
        (KeyError("anything we don't understand"), P),
    ],
)
def test_classify(exc: Exception, kind: FailureKind) -> None:
    assert classify(exc) is kind


class FakeClock:
    """Seconds left in a run that starts with `left`; sleeping and attempts move it."""

    def __init__(self, left: float) -> None:
        self.left = left
        self.sleeps: list[float] = []

    def time_left(self) -> float:
        return max(self.left, 0.0)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.left -= seconds


def failing(errors: list[Exception], clock: FakeClock, took: float = 0.0):
    """An attempt that raises the given errors in order, then returns "ok"."""
    timeouts: list[float] = []

    def attempt(timeout: float) -> str:
        timeouts.append(timeout)
        clock.left -= min(took, timeout)
        if errors:
            raise errors.pop(0)
        return "ok"

    return attempt, timeouts


def test_full_jitter_stays_under_the_capped_backoff() -> None:
    policy, rng = RetryPolicy(max_attempts=6, base_s=0.5, cap_s=4.0), random.Random(7)
    for retry, ceiling in enumerate([0.5, 1.0, 2.0, 4.0, 4.0]):
        waits = [backoff_s(retry, policy, rng) for _ in range(200)]
        assert min(waits) >= 0.0 and max(waits) <= ceiling


def test_a_transient_failure_is_retried_then_succeeds() -> None:
    clock = FakeClock(left=60.0)
    attempt, timeouts = failing([SearchHTTPError(503)], clock)
    result = retry_call(attempt, RetryPolicy(), 10.0, clock.time_left, clock.sleep)
    assert result == "ok" and len(timeouts) == 2 and len(clock.sleeps) == 1


def test_a_permanent_failure_is_tried_once() -> None:
    clock = FakeClock(left=60.0)
    attempt, timeouts = failing([SearchHTTPError(401)], clock)
    with pytest.raises(SearchHTTPError):
        retry_call(attempt, RetryPolicy(), 10.0, clock.time_left, clock.sleep)
    assert len(timeouts) == 1 and clock.sleeps == []


def test_retries_are_bounded_by_max_attempts() -> None:
    clock = FakeClock(left=60.0)
    attempt, timeouts = failing([SearchHTTPError(503)] * 5, clock)
    with pytest.raises(SearchHTTPError):
        retry_call(attempt, RetryPolicy(max_attempts=3), 10.0, clock.time_left, clock.sleep)
    assert len(timeouts) == 3 and len(clock.sleeps) == 2


def test_each_attempt_gets_only_the_time_left() -> None:
    clock = FakeClock(left=12.0)  # the run has 12 s left; SEARCH_TIMEOUT_S is 10
    attempt, timeouts = failing([httpx.ReadTimeout("stalled")] * 3, clock, took=10.0)
    with pytest.raises(httpx.ReadTimeout):
        retry_call(attempt, RetryPolicy(), 10.0, clock.time_left, clock.sleep, random.Random(1))
    assert timeouts[0] == 10.0
    assert timeouts[1] < 2.0  # not a fresh full timeout
    assert clock.left >= 0.0  # never past the run's time left


def test_a_retry_after_longer_than_the_time_left_gives_up_at_once() -> None:
    clock = FakeClock(left=20.0)
    attempt, timeouts = failing([SearchHTTPError(429, retry_after_s=30.0)], clock)
    with pytest.raises(SearchHTTPError):
        retry_call(attempt, RetryPolicy(), 10.0, clock.time_left, clock.sleep)
    assert len(timeouts) == 1 and clock.sleeps == []  # no 30 s wait inside a 20 s run


def test_a_short_retry_after_is_honoured() -> None:
    clock = FakeClock(left=60.0)
    attempt, _ = failing([SearchHTTPError(429, retry_after_s=3.0)], clock)
    retry_call(attempt, RetryPolicy(base_s=0.5), 10.0, clock.time_left, clock.sleep)
    assert clock.sleeps == [3.0]  # the server's wait, longer than our backoff ceiling of 0.5
