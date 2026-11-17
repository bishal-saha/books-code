"""The run budget: hard limits on one agent run, checked by the loop's code, never the model.

New in Chapter 16: money, the fourth limit. RunBudget.max_cost_usd is RUN_MAX_COST_USD; the
tracker prices every model call from models.toml (Chapter 11) and every search request from
SEARCH_USD_PER_QUERY, and the eighth StopCause, cost_limit, ends a run that can't afford its
next model call. Like tokens, the check happens before each call, so the last call can go over
by at most that one call when its input was underestimated (the book's bounded overshoot).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ch16.pricing import MTOK, Price, cost_of


class StopCause(StrEnum):
    FINISHED = "finished"  # the model ended its turn: the only real answer
    TRUNCATED = "truncated"  # one reply was cut off: output cap or full context window
    STEP_LIMIT = "step_limit"  # budget: maximum steps
    TOKEN_LIMIT = "token_limit"  # budget: total tokens for the run
    TIME_LIMIT = "time_limit"  # budget: wall-clock seconds for the run
    UNEXPECTED_STOP = "unexpected_stop"  # a stop reason the loop does not handle
    MODEL_ERROR = "model_error"  # the model call failed after the SDK's retries
    COST_LIMIT = "cost_limit"  # new in Chapter 16. budget: money for the run


@dataclass(frozen=True)
class RunBudget:
    max_steps: int
    max_total_tokens: int  # input + output, summed over every step
    max_wall_seconds: float
    max_cost_usd: Decimal | None = None  # new in Chapter 16; None: no money limit (tests only)


@dataclass(frozen=True)
class CallLimits:
    """Per-call caps, passed in so the loop never reads settings itself."""

    max_output_tokens: int
    timeout_seconds: float
    attempts: int = 1  # new in Chapter 16: MAX_RETRIES + 1, the SDK's tries for one call


@dataclass
class BudgetTracker:
    budget: RunBudget
    clock: Callable[[], float] = time.monotonic  # never jumps when the system clock changes
    price: Price | None = None  # new: the model's price from models.toml
    search_usd_per_query: Decimal | None = None  # new: SEARCH_USD_PER_QUERY
    input_tokens: int = 0
    output_tokens: int = 0
    model_usd: Decimal = Decimal(0)
    search_requests: int = 0  # every request sent, retries included
    started_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()
        if self.budget.max_cost_usd is not None and self.price is None:
            raise ValueError("a money budget needs the model's price (models.toml)")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def search_usd(self) -> Decimal:
        return (self.search_usd_per_query or Decimal(0)) * self.search_requests

    @property
    def spent_usd(self) -> Decimal:
        return self.model_usd + self.search_usd

    def elapsed(self) -> float:
        return self.clock() - self.started_at

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.price is not None:
            self.model_usd += cost_of(input_tokens, output_tokens, self.price)

    def remaining_tokens(self) -> int:
        return max(self.budget.max_total_tokens - self.total_tokens, 0)

    def remaining_seconds(self) -> float:
        return max(self.budget.max_wall_seconds - self.elapsed(), 0.0)

    def remaining_usd(self) -> Decimal | None:
        if self.budget.max_cost_usd is None:
            return None
        return max(self.budget.max_cost_usd - self.spent_usd, Decimal(0))

    def affordable_output_tokens(self, input_tokens: int) -> int | None:
        """Output tokens the money left can pay for after this input; None: no money limit."""
        left = self.remaining_usd()
        if left is None or self.price is None:
            return None
        input_usd = cost_of(input_tokens, 0, self.price)
        if input_usd >= left:
            return 0
        if self.price.output_per_mtok == 0:  # a free model: output never runs out of money
            return None
        return int((left - input_usd) * MTOK / self.price.output_per_mtok)

    def charge_search(self) -> bool:
        """Before a search request is sent: charge it, or return False if money can't cover it."""
        left = self.remaining_usd()
        price = self.search_usd_per_query or Decimal(0)
        if left is not None and price > left:
            return False
        self.search_requests += 1
        return True

    def check(self, min_tokens: int, min_seconds: float) -> StopCause | None:
        """Before a step: is there room for one more useful model call?"""
        if self.remaining_tokens() < min_tokens:
            return StopCause.TOKEN_LIMIT
        if self.remaining_seconds() < min_seconds:
            return StopCause.TIME_LIMIT
        return None

    def describe(self, cause: StopCause) -> str:
        """One line naming the limit that stopped the run, with the numbers."""
        b = self.budget
        match cause:
            case StopCause.STEP_LIMIT:
                return f"step budget: all {b.max_steps} steps used"
            case StopCause.TOKEN_LIMIT:
                return f"token budget: {self.total_tokens:,} of {b.max_total_tokens:,} tokens used"
            case StopCause.TIME_LIMIT:
                return f"time budget: {self.elapsed():.0f} of {b.max_wall_seconds:.0f} s used"
            case StopCause.COST_LIMIT:
                return (
                    f"money budget: ${self.spent_usd:.4f} of ${b.max_cost_usd:.4f} spent, "
                    "too little left for another model call"
                )
            case _:
                return cause.value
