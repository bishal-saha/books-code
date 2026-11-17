"""The context budget inspector: tokens and share per component, for one request."""

import logging
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from ch09.context_budget import ContextBudget
from ch09.model_client import Message, ModelClient, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)
Component = Literal["overhead", "system", "tools", "history", "tool_results"]


class ComponentUsage(BaseModel):
    name: Component
    tokens: int
    share: float  # tokens / total input tokens; shares sum to 1
    ceiling: int | None  # warning only; None means no ceiling configured
    over: bool


class ContextReport(BaseModel):
    components: list[ComponentUsage]
    total_input: int
    output_reserve: int
    window: int
    headroom: int  # window - total_input - output_reserve
    provider_counts: bool  # False if the counts are local estimates

    def tokens(self, name: Component) -> int:
        return next(c.tokens for c in self.components if c.name == name)


class FixedCounts(BaseModel):
    """Counts that cannot change during a run: measured once, then reused."""

    base: int
    with_system: int
    with_tools: int


PLACEHOLDER = [Message(role="user", content=".")]  # a request needs one message


def blank_tool_results(messages: Sequence[Message]) -> list[Message]:
    """A copy with every tool result's content emptied. Removing a result instead would leave
    its tool call unanswered, which makes the request invalid."""
    return [
        m.model_copy(
            update={
                "tool_results": [
                    ToolResult(tool_call_id=r.tool_call_id, content="", is_error=r.is_error)
                    for r in m.tool_results
                ]
            }
        )
        for m in messages
    ]


def count_fixed(
    client: ModelClient,
    system: str,
    tools: Sequence[ToolDefinition],
    timeout: float | None = None,
) -> FixedCounts:
    return FixedCounts(
        base=client.count_tokens("", PLACEHOLDER, (), timeout),
        with_system=client.count_tokens(system, PLACEHOLDER, (), timeout),
        with_tools=client.count_tokens(system, PLACEHOLDER, tools, timeout),
    )


def inspect_request(
    client: ModelClient,
    system: str,
    tools: Sequence[ToolDefinition],
    messages: Sequence[Message],
    fixed: FixedCounts,
    budget: ContextBudget,
    timeout: float | None = None,
) -> ContextReport:
    blanked = client.count_tokens(system, blank_tool_results(messages), tools, timeout)
    full = client.count_tokens(system, messages, tools, timeout)
    raw: dict[Component, int] = {
        "overhead": fixed.base,
        "system": fixed.with_system - fixed.base,
        "tools": fixed.with_tools - fixed.with_system,
        "history": blanked - fixed.with_tools,
        "tool_results": full - blanked,
    }
    return build_report(raw, full, budget, client.provider_counts)


def build_report(
    raw: dict[Component, int], total: int, budget: ContextBudget, provider_counts: bool
) -> ContextReport:
    ceilings: dict[Component, int | None] = {
        "system": budget.system_ceiling,
        "tools": budget.tools_ceiling,
    }
    components = []
    for name, tokens in raw.items():
        ceiling = ceilings.get(name)
        components.append(
            ComponentUsage(
                name=name,
                tokens=tokens,
                share=tokens / total if total else 0.0,
                ceiling=ceiling,
                over=ceiling is not None and tokens > ceiling,
            )
        )
    return ContextReport(
        components=components,
        total_input=total,
        output_reserve=budget.output_reserve,
        window=budget.window,
        headroom=budget.window - total - budget.output_reserve,
        provider_counts=provider_counts,
    )


class ContextInspector:
    """The loop's optional hook: fixed counts once per run, two counts per step after that."""

    def __init__(self, client: ModelClient, budget: ContextBudget) -> None:
        self.client = client
        self.budget = budget
        self._fixed: FixedCounts | None = None

    def inspect(
        self,
        system: str,
        tools: Sequence[ToolDefinition],
        messages: Sequence[Message],
        timeout: float | None = None,
    ) -> ContextReport:
        if self._fixed is None:
            self._fixed = count_fixed(self.client, system, tools, timeout)
        report = inspect_request(
            self.client, system, tools, messages, self._fixed, self.budget, timeout
        )
        for c in report.components:
            if c.over:  # a warning, never a stop: the run budget stops runs
                logger.warning("%s uses %d tokens, over its ceiling of %d", *_over(c))
        if report.headroom < 0:  # the provider will refuse this request: model_error
            logger.warning("request leaves %d tokens of headroom", report.headroom)
        return report


def _over(c: ComponentUsage) -> tuple[str, int, int]:
    return c.name, c.tokens, c.ceiling or 0


def context_table(reports: Sequence[ContextReport]) -> list[str]:
    """Tokens and share per component, one row per step. '!' marks a passed ceiling."""
    names = [c.name for c in reports[0].components] if reports else []
    lines = ["step  " + "".join(f"{n:>15}" for n in names) + f"{'total':>8}{'headroom':>10}"]
    for step, r in enumerate(reports, 1):
        cells = "".join(
            f"{f'{c.tokens} ({c.share:.0%})' + ('!' if c.over else ''):>15}" for c in r.components
        )
        lines.append(f"{step:<6}{cells}{r.total_input:>8}{r.headroom:>10}")
    if reports:
        source = "provider counts" if reports[0].provider_counts else "local estimates"
        lines.append(f"[{source}; window {reports[0].window}, "
                     f"output reserve {reports[0].output_reserve}]")  # fmt: skip
    return lines
