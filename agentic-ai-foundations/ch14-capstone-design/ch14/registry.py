"""Copied unchanged from Chapter 9 (ch09/registry.py): Chapter 8's registry, Chapter 9's rendering.

From Chapter 8: per-field recovery hints, and one line per invalid field in validation errors.
New in Chapter 9: the registry takes the tool-result cap, and every successful output goes
through render_tool_result (ch14/results.py): a provenance header, then the capped content
inside <data> tags. Chapter 8's as_data() and its 8,000-character backstop are gone.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ch14.model_client import ToolCall, ToolDefinition, ToolResult
from ch14.results import render_tool_result

logger = logging.getLogger(__name__)
DEFAULT_RESULT_CHARS = 16_000  # the context budget's cap per tool result (Settings default)


class ToolError(Exception):
    """A tool failure whose message is written to be shown to the model."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    function: Callable[[Any], Any]  # takes the validated args only; bind the rest with partial
    hints: dict[str, str] = field(default_factory=dict)  # change 1: field name -> recovery hint


def _shown(value: object, limit: int = 60) -> str:
    """The value the model sent, cut short so a huge argument isn't copied back."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def validation_message(tool: str, exc: ValidationError, hints: dict[str, str]) -> str:
    """Change 2: one line per invalid field, with the value received and an optional hint."""
    parts = []
    for err in exc.errors(include_url=False):
        name = ".".join(str(p) for p in err["loc"]) or "input"
        if err["type"] == "missing":  # pydantic's input here is the whole dict: don't echo it
            problem = "required, not provided"
        else:
            problem = f"{err['msg']}; got {_shown(err['input'])}"
        hint = hints.get(name, "")
        parts.append(f"{name}: {problem}. {hint}".strip())
    return f"Invalid arguments for {tool}. " + " ".join(parts)


class ToolRegistry:
    def __init__(self, max_result_chars: int = DEFAULT_RESULT_CHARS) -> None:
        self._tools: dict[str, Tool] = {}
        self.max_result_chars = max_result_chars  # new in Chapter 9: the enforced cap

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def args_models(self) -> dict[str, type[BaseModel]]:
        return {name: t.args_model for name, t in self._tools.items()}

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                input_schema=t.args_model.model_json_schema(),
            )
            for t in self._tools.values()
        ]

    def dispatch(self, call: ToolCall) -> ToolResult:
        """Run one tool call. Never raises: every outcome is a result carrying call.id."""
        tool = self._tools.get(call.name)
        if tool is None:
            known = ", ".join(self._tools)
            return ToolResult(
                tool_call_id=call.id,
                content=f"Unknown tool: {call.name}. Available tools: {known}.",
                is_error=True,
            )
        try:
            args = tool.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            message = validation_message(tool.name, exc, tool.hints)
            return ToolResult(tool_call_id=call.id, content=message, is_error=True)
        try:
            output = tool.function(args)
        except ToolError as exc:  # the tool's own message, written for the model
            return ToolResult(tool_call_id=call.id, content=str(exc), is_error=True)
        except httpx.TimeoutException:  # transient: the same call may work next time
            return ToolResult(
                tool_call_id=call.id,
                content=f"{tool.name} timed out. Retry once; if it fails again, report it.",
                is_error=True,
            )
        except Exception as exc:  # deliberate: a tool failure becomes a result, not a crash
            logger.exception("tool %s failed for call %s", tool.name, call.id)
            return ToolResult(
                tool_call_id=call.id,
                content=f"{tool.name} failed ({type(exc).__name__}).",
                is_error=True,
            )
        content, is_error = render_tool_result(  # new in Chapter 9: header, cap, <data>
            call.name, call.arguments, output, self.max_result_chars
        )
        return ToolResult(tool_call_id=call.id, content=content, is_error=is_error)
