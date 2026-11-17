"""run_research: one question, one run. Wires the tools, the prompt, the loop and the checks.

The registry collects the citable set; the loop checks the final answer against it, with one
retry; this function turns the run into one of four outcomes and costs it.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from ch15.agent import Recorder, RunResult, run_agent
from ch15.answer import FinalAnswer
from ch15.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch15.citations import citable_locations
from ch15.final import check_final, retry_message
from ch15.model_client import ModelClient
from ch15.prompts import build_system_prompt
from ch15.settings import Settings
from ch15.state import ConversationState
from ch15.tools import SearchBackend, build_registry

Outcome = Literal["answered", "needs_info", "rejected", "stopped"]


@dataclass
class ResearchResult:
    outcome: Outcome
    run: RunResult
    citable: set[str]  # every location a tool returned in this run
    search_calls: int
    search_usd: Decimal | None  # None: SEARCH_USD_PER_QUERY not set

    @property
    def answer(self) -> FinalAnswer | None:
        return self.run.answer


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
    recorder: Recorder | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ResearchResult:
    budget = RunBudget(settings.run_max_steps, settings.run_max_tokens, settings.run_max_seconds)
    tracker = BudgetTracker(budget, clock=clock)  # shared, so search_web sees the time left
    registry = build_registry(
        settings.exports_dir,
        backend,
        lambda: min(settings.search_timeout_s, tracker.remaining_seconds()),
        settings.tool_result_max_chars,
        citable_from=citable_locations,
    )
    run = run_agent(
        client,
        build_system_prompt(today, settings.prompt_version),
        ConversationState.start(question),
        registry,
        budget,
        CallLimits(settings.max_output_tokens, settings.timeout_seconds),
        settings.context_policy(),
        check=lambda text: check_final(text, registry.citable),  # read at check time
        retry=lambda check: retry_message(check, registry.citable),
        tracker=tracker,
        recorder=recorder,
    )
    searches = sum(  # calls that returned results; an error result is not counted
        c.name == "search_web" and not c.is_error for s in run.steps for c in s.tool_calls
    )
    price = settings.search_usd_per_query
    return ResearchResult(
        outcome=outcome_of(run),
        run=run,
        citable=set(registry.citable),
        search_calls=searches,
        search_usd=None if price is None else price * searches,
    )
