"""The context budget per component: two enforced limits and two warning-only ceilings.

Not the run budget (Chapter 7's budget.py), which is what stops a run.
"""

from pydantic import BaseModel

from ch09.settings import Settings


class ContextBudget(BaseModel):
    window: int  # configured per model, next to the model ID
    output_reserve: int  # enforced by the provider: max output tokens per call
    tool_result_max_chars: int  # enforced by the loop: cap per tool result
    system_ceiling: int | None = None  # tokens; warning only
    tools_ceiling: int | None = None  # tokens; warning only


def context_budget_from(settings: Settings) -> ContextBudget:
    return ContextBudget(
        window=settings.context_window,
        output_reserve=settings.max_output_tokens,
        tool_result_max_chars=settings.tool_result_max_chars,
        system_ceiling=settings.system_ceiling_tokens,
        tools_ceiling=settings.tools_ceiling_tokens,
    )
