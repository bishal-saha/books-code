"""Cap a tool result without losing where it came from: the provenance envelope."""

from datetime import datetime
from html import escape
from typing import Literal

from pydantic import BaseModel

Kind = Literal["file", "url", "tool"]  # "tool": identifiable, never citable
MARKER_ROOM = 64  # space kept for the truncation marker


class ProvenancedResult(BaseModel):
    origin: str  # file path, URL, or tool call
    kind: Kind
    total_chars: int
    shown: list[tuple[int, int]]  # half-open character ranges of the original
    truncated: bool = False
    summarised: bool = False
    fetched_at: datetime | None = None  # set for URLs
    content: str

    def render(self) -> str:
        """Header line from our code, then the content as data (Chapter 4's tag rule)."""
        ranges = ", ".join(f"{start}-{end}" for start, end in self.shown)
        parts = [
            f"origin: {header_safe(self.origin)}",  # URLs and tool arguments come from outside
            f"kind: {self.kind}",
            f"shown: {ranges} of {self.total_chars} chars",
        ]
        if self.fetched_at:
            parts.append(f"fetched: {self.fetched_at.isoformat()}")
        parts += [
            f for f, on in (("truncated", self.truncated), ("summarised", self.summarised)) if on
        ]
        return f"[{' | '.join(parts)}]\n<data>{escape(self.content, quote=False)}</data>"


def header_safe(text: str) -> str:
    """Remove the header's own delimiters, so an origin cannot imitate another field."""
    return " ".join(text.translate(str.maketrans("[]|", "()/")).split())


def cap_result(
    text: str,
    *,
    origin: str,
    kind: Kind,
    max_chars: int,
    offset: int = 0,
    head_share: float = 0.7,
    fetched_at: datetime | None = None,
) -> ProvenancedResult:
    """Bound the content to max_chars, marker included. The header line is extra."""
    if max_chars < 4 * MARKER_ROOM:
        raise ValueError(f"max_chars={max_chars} is too small; use at least {4 * MARKER_ROOM}")
    total = len(text)
    meta = dict(origin=origin, kind=kind, total_chars=total, fetched_at=fetched_at)
    if offset > 0:  # paging: one window from offset, no tail
        if offset >= total:
            raise ValueError(f"offset {offset} is past the end ({total} chars)")
        end = min(offset + max_chars, total)
        return ProvenancedResult(
            **meta, shown=[(offset, end)], truncated=True, content=text[offset:end]
        )
    if total <= max_chars:
        return ProvenancedResult(**meta, shown=[(0, total)], content=text)
    keep = max_chars - MARKER_ROOM
    head_end = int(keep * head_share)
    tail_start = total - (keep - head_end)
    content = (
        text[:head_end]
        + f"\n[truncated: chars {head_end}-{tail_start} omitted]\n"
        + text[tail_start:]
    )
    return ProvenancedResult(
        **meta, shown=[(0, head_end), (tail_start, total)], truncated=True, content=content
    )


def enforce_cap(result: ProvenancedResult, max_chars: int) -> ProvenancedResult:
    """Loop-level guard for envelopes that tools built themselves."""
    if len(result.content) <= max_chars:
        return result
    if result.summarised or len(result.shown) != 1:
        raise ValueError(
            f"{result.origin}: {len(result.content)} chars, over the {max_chars}-char cap, "
            "and not a plain slice to re-cap."
        )
    start = result.shown[0][0]  # one range: the content is a verbatim slice
    return result.model_copy(
        update={
            "content": result.content[:max_chars],
            "shown": [(start, start + max_chars)],
            "truncated": True,
        }
    )
