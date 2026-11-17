"""Chapter 7's run_agent, with an optional context inspector hook. No framework.

New in Chapter 9: pass `inspector` and every step's request is measured just before the model
call; the report goes into the step log. It warns, it never stops a run: the run budget does.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from ch11.budget import BudgetTracker, CallLimits, RunBudget, StopCause
from ch11.inspector import ContextInspector, ContextReport
from ch11.model_client import (
    Message,
    ModelClient,
    ModelError,
    ModelResponse,
    ToolDefinition,
    ToolResult,
    assistant_message,
    tool_results_message,
)
from ch11.registry import ToolRegistry

logger = logging.getLogger(__name__)
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
    context: ContextReport | None = None  # new in Chapter 9: set when an inspector is on


@dataclass
class RunResult:
    cause: StopCause
    final_text: str  # an answer only when cause is FINISHED
    messages: list[Message]
    steps: list[StepRecord] = field(default_factory=list)
    total_tokens: int = 0
    elapsed_seconds: float = 0.0


def step_record(
    index: int,
    sent: int,
    limits: CallLimits,
    response: ModelResponse,
    results: list[ToolResult],
    duration_s: float,
    context: ContextReport | None = None,
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
        context=context,
    )


def run_agent(
    client: ModelClient,
    system: str,
    user_message: str,
    registry: ToolRegistry,
    budget: RunBudget,
    limits: CallLimits,
    clock: Callable[[], float] = time.monotonic,
    inspector: ContextInspector | None = None,
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
        started, context = clock(), None
        if inspector is not None:  # the request about to go out; its time counts too
            timeout = min(limits.timeout_seconds, tracker.remaining_seconds())
            context = measure(inspector, system, tools, messages, timeout)
            cause = tracker.check(MIN_CALL_TOKENS, MIN_CALL_SECONDS)  # measuring took time
            if cause is not None:
                break
        call_limits = CallLimits(  # shrink this call to what the run has left
            max_output_tokens=min(limits.max_output_tokens, tracker.remaining_tokens()),
            timeout_seconds=min(limits.timeout_seconds, tracker.remaining_seconds()),
        )
        sent = len(messages)
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
        tracker.record(response.usage.input_tokens, response.usage.output_tokens)
        messages.append(assistant_message(response))

        results: list[ToolResult] = []
        if response.stop_reason == "tool_call" and response.tool_calls:
            results = [registry.dispatch(call) for call in response.tool_calls]
            messages.append(tool_results_message(results))  # all results, one message
        steps.append(
            step_record(index, sent, call_limits, response, results, clock() - started, context)
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
        messages=messages,
        steps=steps,
        total_tokens=tracker.total_tokens,
        elapsed_seconds=tracker.elapsed(),
    )


def measure(
    inspector: ContextInspector,
    system: str,
    tools: list[ToolDefinition],
    messages: list[Message],
    timeout: float,
) -> ContextReport | None:
    """A failed count is logged and skipped: measuring must never end the run."""
    try:
        return inspector.inspect(system, tools, messages, timeout)
    except ModelError as exc:
        logger.warning("context inspection skipped: %s", exc)
        return None


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


def print_steps(result: RunResult, budget: RunBudget, out: Callable[[str], None] = print) -> None:
    for s in result.steps:
        tools = tool_summary(s.tool_calls)
        out(
            f"step {s.index + 1}  {s.stop_reason:<9} {tools or '-':<26} "
            f"in={s.input_tokens:<6} out={s.output_tokens:<5} {s.duration_ms} ms"
        )
    out(
        f"stopped: {result.cause}  steps {len(result.steps)}/{budget.max_steps}  "
        f"tokens {result.total_tokens}/{budget.max_total_tokens}  "
        f"time {result.elapsed_seconds:.1f}/{budget.max_wall_seconds:.0f} s"
    )
