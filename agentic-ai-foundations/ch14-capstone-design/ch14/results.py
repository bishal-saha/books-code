"""One rendering path for every tool result: the loop-level cap and the provenance header."""

import json

from ch14.truncate import ProvenancedResult, cap_result, enforce_cap


def render_tool_result(name: str, args: dict, output: object, max_chars: int) -> tuple[str, bool]:
    """Called once per successful tool call by the registry. Returns (content, is_error)."""
    if isinstance(output, ProvenancedResult):  # the tool set its own origin
        try:
            return enforce_cap(output, max_chars).render(), False
        except ValueError as exc:
            return str(exc), True
    origin = f"{name}({json.dumps(args, sort_keys=True)})"
    text = output if isinstance(output, str) else json.dumps(output, default=str)
    if not isinstance(output, str) and len(text) > max_chars:
        # Shaped JSON from Chapter 8's tools: never cut it mid-structure.
        return (
            f"{name} returned {len(text)} chars of JSON, over the {max_chars}-char cap. "
            f"If {name} takes paging or filter arguments, call it again asking for less; "
            "otherwise say the result was too large to read."
        ), True
    return cap_result(text, origin=origin, kind="tool", max_chars=max_chars).render(), False
