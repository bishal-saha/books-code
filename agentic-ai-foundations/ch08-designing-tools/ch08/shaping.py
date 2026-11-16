"""Output shaping helpers: truncation with a marker, and pagination over a fetched list."""


def truncate(text: str, max_chars: int, offset: int, tool: str) -> str:
    """Return text[offset:offset+max_chars], with a marker if anything is left."""
    if offset >= len(text) > 0:
        return f"[offset {offset} is past the end; the text has {len(text):,} characters]"
    chunk = text[offset : offset + max_chars]
    shown_end = offset + len(chunk)
    remaining = len(text) - shown_end
    if remaining <= 0:
        return chunk
    return (
        f"{chunk}\n[truncated: {remaining:,} of {len(text):,} characters not shown; "
        f"call {tool} with offset={shown_end} to continue]"
    )


def paginate(rows: list[dict], cursor: str | None, limit: int, cap: int) -> dict:
    """Slice an already-fetched list. The cursor is an offset into it."""
    start = int(cursor) if cursor else 0
    page = rows[start : start + limit]
    end = start + len(page)
    return {
        "items": page,
        "next_cursor": str(end) if end < len(rows) else None,
        "total": len(rows),
        "total_is_capped": len(rows) >= cap,
    }
