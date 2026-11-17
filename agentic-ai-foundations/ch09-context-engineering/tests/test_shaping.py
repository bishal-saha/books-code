"""truncate, paginate and resolve_inside on their own."""

import os

from ch09.paths import resolve_inside
from ch09.shaping import paginate, truncate


def test_truncate_marks_what_is_left():
    out = truncate("a" * 25, max_chars=10, offset=0, tool="get_policy")
    assert out == "a" * 10 + (
        "\n[truncated: 15 of 25 characters not shown; call get_policy with offset=10 to continue]"
    )
    assert truncate("a" * 25, max_chars=10, offset=20, tool="get_policy") == "a" * 5
    assert "past the end" in truncate("a" * 25, max_chars=10, offset=40, tool="get_policy")


def test_paginate_reports_the_next_cursor_and_the_cap():
    rows = [{"n": n} for n in range(5)]
    assert paginate(rows, None, 2, cap=500)["next_cursor"] == "2"
    last = paginate(rows, "4", 2, cap=500)
    assert last["items"] == [{"n": 4}] and last["next_cursor"] is None
    assert paginate(rows, None, 2, cap=5)["total_is_capped"] is True


def test_resolve_inside_rejects_escapes(tmp_path):
    folder = tmp_path / "allowed"
    folder.mkdir()
    (folder / "notes.md").write_text("ok")
    os.symlink(tmp_path, folder / "link")
    assert resolve_inside(folder, "notes.md") == (folder / "notes.md").resolve()
    assert resolve_inside(folder, "../secrets") is None
    assert resolve_inside(folder, "/etc/passwd") is None
    assert resolve_inside(folder, "link/other.md") is None
