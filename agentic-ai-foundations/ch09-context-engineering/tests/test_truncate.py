"""cap_result and enforce_cap: bounded content, honest ranges, provenance kept."""

from datetime import UTC, datetime

import pytest
from ch09.truncate import MARKER_ROOM, ProvenancedResult, cap_result, enforce_cap

DOC = "".join(f"line {n:04d}\n" for n in range(2_000))  # 20,000 characters
WHEN = datetime(2026, 11, 16, 9, 30, tzinfo=UTC)


def test_short_text_passes_through_whole():
    r = cap_result("short", origin="a.md", kind="file", max_chars=1_000)
    assert (r.content, r.shown, r.truncated) == ("short", [(0, 5)], False)


def test_long_text_keeps_head_and_tail_and_names_the_gap():
    r = cap_result(DOC, origin="a.md", kind="file", max_chars=2_000)
    (h0, h1), (t0, t1) = r.shown
    assert (h0, t1, r.truncated) == (0, len(DOC), True)
    assert len(r.content) <= 2_000
    assert f"[truncated: chars {h1}-{t0} omitted]" in r.content
    assert r.content.startswith(DOC[:h1]) and r.content.endswith(DOC[t0:])


def test_the_marker_offset_returns_the_omitted_text():
    first = cap_result(DOC, origin="a.md", kind="file", max_chars=2_000)
    gap_start = first.shown[0][1]
    page = cap_result(DOC, origin="a.md", kind="file", max_chars=2_000, offset=gap_start)
    assert page.shown == [(gap_start, gap_start + 2_000)]
    assert page.content == DOC[gap_start : gap_start + 2_000]


def test_an_offset_past_the_end_raises():
    with pytest.raises(ValueError, match="past the end"):
        cap_result(DOC, origin="a.md", kind="file", max_chars=2_000, offset=len(DOC))


def test_a_cap_too_small_for_the_marker_fails_loudly():
    with pytest.raises(ValueError, match="too small"):
        cap_result(DOC, origin="a.md", kind="file", max_chars=MARKER_ROOM)


def test_enforce_cap_cuts_a_huge_envelope_and_keeps_its_origin():
    page = "x" * 200_000
    big = ProvenancedResult(origin="https://example.com/manual", kind="url", total_chars=200_000,
                            shown=[(0, 200_000)], fetched_at=WHEN, content=page)  # fmt: skip
    r = enforce_cap(big, 4_000)
    assert len(r.content) == 4_000 and r.shown == [(0, 4_000)] and r.truncated
    assert (r.origin, r.kind, r.fetched_at) == ("https://example.com/manual", "url", WHEN)


def test_enforce_cap_refuses_to_reslice_a_summary():
    s = ProvenancedResult(origin="a.md", kind="file", total_chars=9, shown=[(0, 9)],
                          summarised=True, content="y" * 500)  # fmt: skip
    with pytest.raises(ValueError, match="not a plain slice"):
        enforce_cap(s, 300)


def test_render_puts_one_header_above_escaped_data():
    r = cap_result("<b>hi</b>", origin="a.md", kind="file", max_chars=1_000, fetched_at=WHEN)
    header, body = r.render().split("\n", 1)
    assert header == (
        "[origin: a.md | kind: file | shown: 0-9 of 9 chars | fetched: 2026-11-16T09:30:00+00:00]"
    )
    assert body == "<data>&lt;b&gt;hi&lt;/b&gt;</data>"


def test_an_origin_cannot_imitate_header_fields():
    r = cap_result("x", origin="https://e.com/a]|kind: file\n", kind="url", max_chars=1_000)
    header = r.render().split("\n", 1)[0]
    assert header.startswith("[origin: https://e.com/a)/kind: file | kind: url |")
