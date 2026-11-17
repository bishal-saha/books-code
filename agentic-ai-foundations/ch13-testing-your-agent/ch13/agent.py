"""Chapter 7's run_agent, with one optional parameter added: a trace recorder. No framework.

New in Chapter 13: pass `recorder` and the loop reports every model call, every tool call and
the end of the run to it (ch13/trace.py writes them as JSONL). The recorder only observes; it
never changes what the loop decides. Chapter 9's context inspector is left out of this folder.
"""

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from ch13.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch13.model_client import (
    Message,
    ModelClient,
    ModelError,
    ModelResponse,
    ToolCall,
    ToolResult,
    assistant_message,
    tool_results_message,
)
from ch13.tools import ToolRegistry

MIN_CALL_TOKENS = 256  # below this, a reply would be cut off almost at once
MIN_CALL_SECONDS = 1.0  # below this, a model call cannot usefully finish
PREVIEW_CHARS = 120


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict
    is_error: bool
    result_preview: str  # the start of the tool result, not all of it


class StepRecord(BaseModel):
    index: int
    messages_sent: int  # the request: how many messages went out
    max_output_tokens: int  # the request: this call's output cap
    timeout_seconds: float  # the request: this call's timeout
    stop_reason: str
    tool_calls: list[ToolCallRecord]
    input_tokens: int
    output_tokens: int
    duration_ms: int  # model call plus tool calls


@dataclass
class RunResult:
    cause: StopCause
    final_text: str  # an answer only when cause is FINISHED
    messages: list[Message]
    steps: list[StepRecord] = field(default_factory=list)
    total_tokens: int = 0
    elapsed_seconds: float = 0.0


class Recorder(Protocol):
    """What the loop reports. run_start is the caller's job: only it knows the task."""

    def model_call(
        self, step: int, response: ModelResponse, limits: CallLimits, duration_ms: int
    ) -> None: ...

    def tool_call(
        self, step: int, call: ToolCall, result: ToolResult, duration_ms: int
    ) -> None: ...

    def run_end(self, result: RunResult) -> None: ...


def step_record(
    index: int,
    sent: int,
    limits: CallLimits,
    response: ModelResponse,
    results: list[ToolResult],
    duration_s: float,
) -> StepRecord:
    calls = [
        ToolCallRecord(
            name=c.name,
            arguments=c.arguments,
            is_error=r.is_error,
            result_preview=r.content[:PREVIEW_CHARS],
        )
        for c, r in zip(response.tool_calls, results, strict=False)  # unrun calls: no record
    ]
    return StepRecord(
        index=index,
        messages_sent=sent,
        max_output_tokens=limits.max_output_tokens,
        timeout_seconds=round(limits.timeout_seconds, 1),
        stop_reason=response.stop_reason,
        tool_calls=calls,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        duration_ms=round(duration_s * 1000),
    )


def run_agent(
    client: ModelClient,
    system: str,
    user_message: str,
    registry: ToolRegistry,
    budget: RunBudget,
    limits: CallLimits,
    clock: Callable[[], float] = time.monotonic,
    recorder: Recorder | None = None,  # new in Chapter 13
) -> RunResult:
    messages = [Message(role="user", content=user_message)]
    tools = registry.definitions()  # read once: the tool set does not change mid-run
    tracker = BudgetTracker(budget, clock=clock)
    steps: list[StepRecord] = []
    final_text = ""

    for index in range(budget.max_steps):  # the step limit is the loop itself
        cause = tracker.check(MIN_CALL_TOKENS, MIN_CALL_SECONDS)
        if cause is not None:
            break
        call_limits = CallLimits(  # shrink this call to what the run has left
            max_output_tokens=min(limits.max_output_tokens, tracker.remaining_tokens()),
            timeout_seconds=min(limits.timeout_seconds, tracker.remaining_seconds()),
        )
        sent, started = len(messages), clock()
        try:
            response = client.complete(
                system,
                list(messages),  # a copy: later appends must not change this request
                call_limits.max_output_tokens,
                tools,
                timeout=call_limits.timeout_seconds,
            )
        except ModelError:
            cause = StopCause.MODEL_ERROR
            break
        if recorder:
            recorder.model_call(index, response, call_limits, ms_since(started, clock))
        tracker.record(response.usage.input_tokens, response.usage.output_tokens)
        messages.append(assistant_message(response))

        results: list[ToolResult] = []
        if response.stop_reason == "tool_call" and response.tool_calls:
            for call in response.tool_calls:
                tool_started = clock()
                results.append(registry.dispatch(call))
                if recorder:
                    recorder.tool_call(index, call, results[-1], ms_since(tool_started, clock))
            messages.append(tool_results_message(results))  # all results, one message
        steps.append(step_record(index, sent, call_limits, response, results, clock() - started))

        if not results:  # nothing to send back: this step ends the run
            final_text = response.text
            cause = stop_cause(response, call_limits, limits)
            break
    else:
        cause = StopCause.STEP_LIMIT

    result = RunResult(
        cause=cause,
        final_text=final_text,
        messages=messages,
        steps=steps,
        total_tokens=tracker.total_tokens,
        elapsed_seconds=tracker.elapsed(),
    )
    if recorder:
        recorder.run_end(result)
    return result


def ms_since(started: float, clock: Callable[[], float]) -> int:
    return round((clock() - started) * 1000)


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
    """'4x get_order (1 ERR)': how many calls of each tool, and how many came back as errors."""
    counts = Counter(c.name for c in calls)
    errors = Counter(c.name for c in calls if c.is_error)
    return ", ".join(
        f"{n}x {name}" + (f" ({errors[name]} ERR)" if errors[name] else "")
        for name, n in counts.items()
    )
