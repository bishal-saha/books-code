"""The run budget: hard limits on one agent run, checked by the loop's code, never the model."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class StopCause(StrEnum):
    FINISHED = "finished"  # the model ended its turn: the only real answer
    TRUNCATED = "truncated"  # one reply was cut off: output cap or full context window
    STEP_LIMIT = "step_limit"  # budget: maximum steps
    TOKEN_LIMIT = "token_limit"  # budget: total tokens for the run
    TIME_LIMIT = "time_limit"  # budget: wall-clock seconds for the run
    UNEXPECTED_STOP = "unexpected_stop"  # a stop reason the loop does not handle
    MODEL_ERROR = "model_error"  # the model call failed after the SDK's retries


@dataclass(frozen=True)
class RunBudget:
    max_steps: int
    max_total_tokens: int  # input + output, summed over every step
    max_wall_seconds: float
    # Money is the fourth limit: Chapter 14 designs it, Chapter 16 enforces it.


@dataclass(frozen=True)
class CallLimits:
    """Per-call caps, passed in so the loop never reads settings itself."""

    max_output_tokens: int
    timeout_seconds: float


@dataclass
class BudgetTracker:
    budget: RunBudget
    clock: Callable[[], float] = time.monotonic  # never jumps when the system clock changes
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def elapsed(self) -> float:
        return self.clock() - self.started_at

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def remaining_tokens(self) -> int:
        return max(self.budget.max_total_tokens - self.total_tokens, 0)

    def remaining_seconds(self) -> float:
        return max(self.budget.max_wall_seconds - self.elapsed(), 0.0)

    def check(self, min_tokens: int, min_seconds: float) -> StopCause | None:
        """Before a step: is there room for one more useful model call?"""
        if self.remaining_tokens() < min_tokens:
            return StopCause.TOKEN_LIMIT
        if self.remaining_seconds() < min_seconds:
            return StopCause.TIME_LIMIT
        return None
