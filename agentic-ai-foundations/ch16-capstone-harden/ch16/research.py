"""run_research: one question, one run. Wires the tools, the prompt, the loop and the checks.

The registry collects the citable set; the loop checks the final answer against it, with one
retry; this function turns the run into one of four outcomes and costs it.
New in Chapter 16: the run budget includes money (RUN_MAX_COST_USD, priced from models.toml
and SEARCH_USD_PER_QUERY), search_web gets its retry policy and the run's tracker, and a
stopped run carries `stop_detail` (which limit, with the numbers) and `gathered` (what the
tools returned before the stop, unchecked).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from ch16.agent import Recorder, RunResult, run_agent
from ch16.answer import FinalAnswer
from ch16.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch16.citations import citable_locations
from ch16.final import check_final, retry_message
from ch16.model_client import ModelClient
from ch16.pricing import Price
from ch16.prompts import build_system_prompt
from ch16.settings import Settings
from ch16.state import ConversationState
from ch16.tools import SearchBackend, SearchRetries, build_registry

Outcome = Literal["answered", "needs_info", "rejected", "stopped"]


@dataclass
class ResearchResult:
    outcome: Outcome
    run: RunResult
    citable: set[str]  # every location a tool returned in this run
    search_requests: int  # new: every request sent, retries included
    model_usd: Decimal | None  # None: the model is unpriced (tests without a money budget)
    search_usd: Decimal | None  # None: SEARCH_USD_PER_QUERY not set
    budget_usd: Decimal | None  # new: the run's money budget; None when unpriced

    @property
    def answer(self) -> FinalAnswer | None:
        return self.run.answer

    @property
    def gathered(self) -> list[str]:
        """New: for a stopped run, the locations tools returned. Unchecked, never an answer."""
        return sorted(self.citable) if self.outcome == "stopped" else []


def outcome_of(run: RunResult) -> Outcome:
    if run.cause is not StopCause.FINISHED:
        return "stopped"  # a budget limit or another stop: never an answer
    if run.answer is None:
        return "rejected"  # the final answer failed its checks twice
    return run.answer.status  # "answered" (possibly with `missing`) or "needs_info"


def run_research(
    question: str,
    today: date,
    settings: Settings,
    client: ModelClient,
    backend: SearchBackend,
    price: Price | None = None,  # new: the configuration's price from models.toml
    recorder: Recorder | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,  # new: search retries wait with this
) -> ResearchResult:
    budget = RunBudget(
        settings.run_max_steps,
        settings.run_max_tokens,
        settings.run_max_seconds,
        settings.run_max_cost_usd if price else None,  # unpriced: the CLI refuses to start
    )
    tracker = BudgetTracker(  # shared: search_web reads the time left and pays from it
        budget, clock=clock, price=price, search_usd_per_query=settings.search_usd_per_query
    )
    search = SearchRetries(settings.search_timeout_s, settings.retry_policy(), tracker, sleep)
    registry = build_registry(
        settings.exports_dir,
        backend,
        search,
        settings.tool_result_max_chars,
        citable_from=citable_locations,
    )
    run = run_agent(
        client,
        build_system_prompt(today, settings.prompt_version),
        ConversationState.start(question),
        registry,
        budget,
        CallLimits(settings.max_output_tokens, settings.timeout_seconds, settings.max_retries + 1),
        settings.context_policy(),
        check=lambda text: check_final(text, registry.citable),  # read at check time
        retry=lambda check: retry_message(check, registry.citable),
        tracker=tracker,
        recorder=recorder,
    )
    search_price = settings.search_usd_per_query
    return ResearchResult(
        outcome=outcome_of(run),
        run=run,
        citable=set(registry.citable),
        search_requests=tracker.search_requests,
        model_usd=tracker.model_usd if price else None,
        search_usd=None if search_price is None else tracker.search_usd,
        budget_usd=budget.max_cost_usd,
    )
