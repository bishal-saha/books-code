"""render_tool_result: one header per result, JSON never cut mid-structure."""

from ch09.results import render_tool_result
from ch09.truncate import ProvenancedResult


def test_an_envelope_gets_exactly_one_header():
    env = ProvenancedResult(origin="a.md", kind="file", total_chars=5, shown=[(0, 5)],
                            content="hello")  # fmt: skip
    content, is_error = render_tool_result("read_doc", {"path": "a.md"}, env, 1_000)
    assert not is_error and content.count("[origin:") == 1
    assert content == "[origin: a.md | kind: file | shown: 0-5 of 5 chars]\n<data>hello</data>"


def test_plain_data_gets_a_tool_origin_from_name_and_arguments():
    content, _ = render_tool_result("get_order", {"order_id": "O-1"}, {"status": "shipped"}, 1_000)
    assert content.startswith('[origin: get_order({"order_id": "O-1"}) | kind: tool |')


def test_oversized_json_is_an_error_result_not_a_cut():
    rows = [{"id": n, "carrier": "Swiftway Parcel"} for n in range(500)]
    content, is_error = render_tool_result("list_shipments", {}, rows, 2_000)
    assert is_error and "over the 2000-char cap" in content and "<data>" not in content


def test_a_long_plain_string_is_capped_with_its_origin():
    content, is_error = render_tool_result("tail_log", {}, "z" * 10_000, 2_000)
    assert not is_error and "| truncated]" in content.splitlines()[0]
