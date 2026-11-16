"""Chapter 9's run_agent, now over a ConversationState with a context policy. No framework.

New in Chapter 10: run_agent takes and returns a ConversationState instead of building a list,
and manage_context trims or compacts the history before every model call. Each step record
carries what manage_context did (`context`). Chapter 9's inspector hook is left out here.
"""

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from ch10.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch10.model_client import ModelClient, ModelError, ModelResponse, ToolResult
from ch10.state import (
    CompactionReport,
    ContextPolicy,
    ConversationState,
    TrimReport,
    check_pairing,
    compact,
    history_tokens,
    trim_to_target,
)
from ch10.tools import ToolRegistry

MIN_CALL_TOKENS = 256  # below this, a reply would be cut off almost at once
MIN_CALL_SECONDS = 1.0  # below this, a model call cannot usefully finish
PREVIEW_CHARS = 120

ContextEvent = TrimReport | CompactionReport


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict
    is_error: bool
    result_preview: str  # the start of the tool result, not all of it


class StepRecord(BaseModel):
    index: int
    messages_sent: int
    history_tokens: int  # new in Chapter 10: the history as sent, after manage_context
    max_output_tokens: int
    timeout_seconds: float
    stop_reason: str
    tool_calls: list[ToolCallRecord]
    input_tokens: int
    output_tokens: int
    duration_ms: int  # context management, model call and tool calls
    context: ContextEvent | None = None  # new in Chapter 10: a trim or a compaction


@dataclass
class RunResult:
    cause: StopCause
    final_text: str  # an answer only when cause is FINISHED
    state: ConversationState  # continue a session from this, never from the state you passed
    steps: list[StepRecord] = field(default_factory=list)
    total_tokens: int = 0
    elapsed_seconds: float = 0.0


def manage_context(
    state: ConversationState,
    client: ModelClient,
    policy: ContextPolicy,
    tracker: BudgetTracker,
    timeout: float,
) -> tuple[ConversationState, int, ContextEvent | None]:
    """Runs before every model call. Returns the state to send, its size and what happened."""
    tokens = history_tokens(state, client, timeout)
    event: ContextEvent | None = None

    if policy.strategy == "compact" and tokens > policy.compaction_threshold_tokens:
        if tracker.remaining_tokens() >= tokens + policy.compaction_max_tokens:  # rough bound
            state, event = compact(state, client, policy, tokens, timeout)
            if event.usage:  # the summary call is paid from the run budget
                tracker.record(event.usage.input_tokens, event.usage.output_tokens)
        else:  # the run cannot afford a summary call
            state, event = trim_to_target(
                state, client, policy.compaction_threshold_tokens, tokens, timeout
            )
        tokens = event.tokens_after

    if tokens > policy.trim_target_tokens:  # safety net for both strategies
        state, event = trim_to_target(state, client, policy.trim_target_tokens, tokens, timeout)
        tokens = event.tokens_after
    return state, tokens, event


def run_agent(
    client: ModelClient,
    system: str,
    state: ConversationState,
    registry: ToolRegistry,
    budget: RunBudget,
    limits: CallLimits,
    policy: ContextPolicy,
    clock: Callable[[], float] = time.monotonic,
) -> RunResult:
    if problems := check_pairing(state):  # a caller bug: refuse before the run starts
        raise ValueError(f"malformed conversation state: {'; '.join(problems)}")
    state = state.model_copy(deep=True)  # the caller's object is never changed
    tools = registry.definitions()
    tracker = BudgetTracker(budget, clock=clock)
    steps: list[StepRecord] = []
    final_text = ""

    for index in range(budget.max_steps):  # the step limit is the loop itself
        cause = tracker.check(MIN_CALL_TOKENS, MIN_CALL_SECONDS)
        if cause is not None:
            break
        started = clock()
        try:
            timeout = min(limits.timeout_seconds, tracker.remaining_seconds())
            state, tokens, event = manage_context(state, client, policy, tracker, timeout)
            cause = tracker.check(MIN_CALL_TOKENS, MIN_CALL_SECONDS)  # it took time and tokens
            if cause is not None:
                break
            call_limits = CallLimits(  # shrink this call to what the run has left
                max_output_tokens=min(limits.max_output_tokens, tracker.remaining_tokens()),
                timeout_seconds=min(limits.timeout_seconds, tracker.remaining_seconds()),
            )
            sent = state.to_messages()
            response = client.complete(
                system,
                sent,
                call_limits.max_output_tokens,
                tools,
                timeout=call_limits.timeout_seconds,
            )
        except ModelError:  # a failed count or a failed completion ends the run the same way
            cause = StopCause.MODEL_ERROR
            break
        tracker.record(response.usage.input_tokens, response.usage.output_tokens)
        state.add_assistant(response)

        results: list[ToolResult] = []
        if response.stop_reason == "tool_call" and response.tool_calls:
            results = [registry.dispatch(call) for call in response.tool_calls]
            state.add_tool_results(results)  # all results, one message
        steps.append(
            step_record(
                index, len(sent), tokens, call_limits, response, results, clock() - started, event
            )
        )
        if not results:  # nothing to send back: this step ends the run
            final_text = response.text
            cause = stop_cause(response, call_limits, limits)
            break
    else:
        cause = StopCause.STEP_LIMIT

    return RunResult(
        cause=cause,
        final_text=final_text,
        state=state,
        steps=steps,
        total_tokens=tracker.total_tokens,
        elapsed_seconds=tracker.elapsed(),
    )


def step_record(
    index: int,
    sent: int,
    tokens: int,
    limits: CallLimits,
    response: ModelResponse,
    results: list[ToolResult],
    duration_s: float,
    event: ContextEvent | None,
) -> StepRecord:
    calls = [
        ToolCallRecord(
            name=c.name,
            arguments=c.arguments,
            is_error=r.is_error,
            result_preview=r.content[:PREVIEW_CHARS],
        )
        for c, r in zip(response.tool_calls, results, strict=False)
    ]
    return StepRecord(
        index=index,
        messages_sent=sent,
        history_tokens=tokens,
        max_output_tokens=limits.max_output_tokens,
        timeout_seconds=round(limits.timeout_seconds, 1),
        stop_reason=response.stop_reason,
        tool_calls=calls,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        duration_ms=round(duration_s * 1000),
        context=event,
    )


def stop_cause(response: ModelResponse, used: CallLimits, configured: CallLimits) -> StopCause:
    match response.stop_reason:
        case "finished":
            return StopCause.FINISHED
        case "truncated" if used.max_output_tokens < configured.max_output_tokens:
            return StopCause.TOKEN_LIMIT  # the budget's remainder was the cap that cut it
        case "truncated":
            return StopCause.TRUNCATED
        case _:  # "other", or "tool_call" with no calls to run
            return StopCause.UNEXPECTED_STOP


def tool_summary(calls: list[ToolCallRecord]) -> str:
    counts = Counter(c.name for c in calls)
    return ", ".join(f"{n}x {name}" for name, n in counts.items())
