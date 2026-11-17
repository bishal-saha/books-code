"""New in Chapter 16: bounded retries with exponential backoff and full jitter.

Only transient failures are retried. Every attempt gets min(attempt timeout, time left), and the
helper never sleeps past the run's time left: a retry spends the same run budget as the call.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from ch16.failures import FailureKind, classify

MIN_ATTEMPT_S = 1.0  # below this, an attempt cannot usefully finish


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3  # SEARCH_RETRY_ATTEMPTS: the first try plus two retries
    base_s: float = 0.5  # SEARCH_RETRY_BASE_S
    cap_s: float = 4.0  # SEARCH_RETRY_CAP_S: no single wait is longer


def backoff_s(retry: int, policy: RetryPolicy, rng: random.Random) -> float:
    """Full jitter: a random wait between 0 and min(cap, base * 2**retry); retry counts from 0."""
    return rng.uniform(0.0, min(policy.cap_s, policy.base_s * 2**retry))


def retry_call[T](
    attempt: Callable[[float], T],  # takes this attempt's timeout in seconds
    policy: RetryPolicy,
    attempt_timeout_s: float,
    time_left: Callable[[], float],  # the run's remaining seconds (BudgetTracker)
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> T:
    rng = rng or random.Random()
    for n in range(policy.max_attempts):
        try:
            return attempt(min(attempt_timeout_s, time_left()))
        except Exception as exc:
            if classify(exc) is FailureKind.PERMANENT or n + 1 == policy.max_attempts:
                raise  # permanent: retrying can't help; transient: out of attempts
            wait = backoff_s(n, policy, rng)
            hinted = getattr(exc, "retry_after_s", None)  # the server knows its own state
            if hinted is not None:
                wait = max(wait, hinted)
            if wait + MIN_ATTEMPT_S > time_left():  # no time to wait and then make an attempt
                raise
            sleep(wait)
    raise ValueError("policy.max_attempts must be at least 1")
