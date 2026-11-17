"""The capstone's agent loop: Chapter 10's run_agent with Chapter 13's recorder. No framework.

Copied from Chapter 10: the loop runs over a ConversationState, and manage_context trims or
compacts the history before every model call (Chapter 10's context policy).
Copied from Chapter 13: an optional recorder sees every model call and tool call.
New in Chapter 15:
- `check` and `retry`: when the model ends its turn, check(text) validates the final answer
  and its citations. A failure gets one retry message, which counts as a step and is paid from
  the same run budget.
- A final answer that still fails after its retry: the run ends with StopCause FINISHED (the
  model did end its turn) and RunResult.answer = None, with the errors in answer_errors. The
  rejected text stays in final_text for the trace; the caller reports the run as rejected and
  never prints that text as an answer.
- The time budget is also checked right after tool calls, so a slow tool ends the run as
  time_limit before another model call starts.
- The caller may pass the BudgetTracker, so a tool (search_web) can read the time left.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from ch15.answer import FinalAnswer
from ch15.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch15.final import FinalCheck
from ch15.model_client import ModelClient, ModelError, ModelResponse, ToolCall, ToolResult
from ch15.registry import ToolRegistry
from ch15.state import (
    CompactionReport,
    ContextPolicy,
    ConversationState,
    TrimReport,
    check_pairing,
    compact,
    history_tokens,
    trim_to_target,
)

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
    history_tokens: int  # the history as sent, after manage_context
    max_output_tokens: int
    timeout_seconds: float
    stop_reason: str
    tool_calls: list[ToolCallRecord]
    input_tokens: int
    output_tokens: int
    duration_ms: int
    context: ContextEvent | None = None  # a trim or a compaction before this call
    answer_errors: list[str] = []  # new in Chapter 15: a final answer this step that failed


@dataclass
class RunResult:
    cause: StopCause
    final_text: str  # the model's last message when cause is FINISHED, accepted or not
    state: ConversationState
    steps: list[StepRecord] = field(default_factory=list)
    total_tokens: int = 0
    elapsed_seconds: float = 0.0
    answer: FinalAnswer | None = None  # new: set only when the final answer was accepted
    answer_errors: list[str] = field(default_factory=list)  # new: why it was rejected
    answer_retries: int = 0  # new: retries used (0 or 1)


class Recorder(Protocol):
    """What the loop reports. run_start and run_end are the caller's job: only it knows the
    task, the citable set and how the run is reported."""

    def model_call(
        self, step: int, response: ModelResponse, limits: CallLimits, duration_ms: int
    ) -> None: ...

    def tool_call(
        self, step: int, call: ToolCall, result: ToolResult, duration_ms: int
    ) -> None: ...

    def context(self, step: int, event: ContextEvent) -> None: ...

    def final_check(self, step: int, check: FinalCheck) -> None: ...


def manage_context(
    state: ConversationState,
    client: ModelClient,
    policy: ContextPolicy,
    tracker: BudgetTracker,
    timeout: float,
) -> tuple[ConversationState, int, ContextEvent | None]:
    """Copied from Chapter 10: runs before every model call."""
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
    check: Callable[[str], FinalCheck] | None = None,  # new in Chapter 15
    retry: Callable[[FinalCheck], str] | None = None,
    max_answer_retries: int = 1,
    tracker: BudgetTracker | None = None,
    clock: Callable[[], float] = time.monotonic,
    recorder: Recorder | None = None,
) -> RunResult:
    if problems := check_pairing(state):  # a caller bug: refuse before the run starts
        raise ValueError(f"malformed conversation state: {'; '.join(problems)}")
    state = state.model_copy(deep=True)  # the caller's object is never changed
    tools = registry.definitions()
    tracker = tracker or BudgetTracker(budget, clock=clock)
    steps: list[StepRecord] = []
    final_text, answer, answer_errors, retries = "", None, [], 0

    for index in range(budget.max_steps):  # the step limit is the loop itself
        cause = tracker.check(MIN_CALL_TOKENS, MIN_CALL_SECONDS)
        if cause is not None:
            break
        started = tracker.clock()
        try:
            timeout = min(limits.timeout_seconds, tracker.remaining_seconds())
            state, tokens, event = manage_context(state, client, policy, tracker, timeout)
            if event and recorder:
                recorder.context(index, event)
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
        if recorder:
            recorder.model_call(index, response, call_limits, ms_since(started, tracker.clock))
        tracker.record(response.usage.input_tokens, response.usage.output_tokens)
        state.add_assistant(response)

        results: list[ToolResult] = []
        if response.stop_reason == "tool_call" and response.tool_calls:
            for call in response.tool_calls:
                tool_started = tracker.clock()
                results.append(registry.dispatch(call))
                if recorder:
                    recorder.tool_call(
                        index, call, results[-1], ms_since(tool_started, tracker.clock)
                    )
            state.add_tool_results(results)  # all results, one message

        verdict = None
        if not results and response.stop_reason == "finished" and check is not None:
            verdict = check(response.text)
            if recorder:
                recorder.final_check(index, verdict)
        steps.append(
            step_record(
                index,
                len(sent),
                tokens,
                call_limits,
                response,
                results,
                started,
                tracker,
                event,
                verdict.errors if verdict else [],
            )
        )

        if results:  # new in Chapter 15: a slow tool can end the run before the next call
            if tracker.remaining_seconds() < MIN_CALL_SECONDS:
                cause = StopCause.TIME_LIMIT
                break
            continue
        final_text = response.text
        cause = stop_cause(response, call_limits, limits)
        if verdict is None:  # not a finished turn, or nothing to check
            break
        if verdict.accepted:
            answer = verdict.answer
            break
        if retries < max_answer_retries and retry is not None:
            retries += 1
            state.add_user(retry(verdict))  # the retry is the next step, same budget
            continue
        answer_errors = verdict.errors  # rejected after its retry: no answer
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
        answer=answer if cause is StopCause.FINISHED else None,
        answer_errors=answer_errors,
        answer_retries=retries,
    )


def ms_since(started: float, clock: Callable[[], float]) -> int:
    return round((clock() - started) * 1000)


def step_record(
    index: int,
    sent: int,
    tokens: int,
    limits: CallLimits,
    response: ModelResponse,
    results: list[ToolResult],
    started: float,
    tracker: BudgetTracker,
    event: ContextEvent | None,
    answer_errors: list[str],
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
        duration_ms=ms_since(started, tracker.clock),
        context=event,
        answer_errors=answer_errors,
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
