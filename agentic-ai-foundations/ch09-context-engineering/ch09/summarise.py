"""Summarise one oversized tool result, keeping its origin. Opt-in per tool; never automatic."""

import logging
from datetime import datetime
from html import escape

from ch09.model_client import Message, ModelClient, ModelError, Usage
from ch09.prompts import load_prompt
from ch09.truncate import Kind, ProvenancedResult, cap_result

logger = logging.getLogger(__name__)


def summarise_result(
    client: ModelClient,
    text: str,
    *,
    origin: str,
    kind: Kind,
    max_chars: int,
    max_input_chars: int,
    max_tokens: int,
    timeout: float | None = None,  # pass what the run has left (Chapter 7)
    fetched_at: datetime | None = None,
) -> tuple[ProvenancedResult, Usage | None]:
    """Returns (result, usage); the caller adds usage to the run budget.
    Falls back to cap_result instead of failing."""
    fallback = cap_result(
        text, origin=origin, kind=kind, max_chars=max_chars, fetched_at=fetched_at
    )
    if len(text) > max_input_chars:  # too large for the summarising call itself
        return fallback, None
    try:
        reply = client.complete(
            load_prompt("summarise", 1).body,
            [Message(role="user", content=f"<data>\n{escape(text, quote=False)}\n</data>")],
            max_tokens,
            timeout=timeout,
        )
    except ModelError as exc:  # Chapter 3's errors, after the SDK's retries
        logger.warning("summary of %s failed (%s); falling back to a cap", origin, exc.kind)
        return fallback, None
    if reply.stop_reason != "finished":  # cut off or odd: not a complete summary
        logger.warning("summary of %s ended with %s; falling back", origin, reply.stop_reason)
        return fallback, reply.usage
    if len(reply.text) > max_chars:  # complete but over the cap: the registry would refuse it
        logger.warning("summary of %s is over the %d-char cap; falling back", origin, max_chars)
        return fallback, reply.usage
    result = ProvenancedResult(
        origin=origin,
        kind=kind,
        total_chars=len(text),
        fetched_at=fetched_at,
        shown=[(0, len(text))],  # the range summarised; none of it verbatim
        summarised=True,
        content=reply.text,
    )
    return result, reply.usage
