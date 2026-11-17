"""Check the design's numbers against the real exports, prompt and tool definitions.

    uv run python -m ch14.design_check --today 2026-01-15

Three questions, answered from files, not guesses: can the model read one quarter of
shipments page by page (no: hence count_rows), how big is the fixed part of every call, and
does the carrier question's walk-through fit the run budget? Token figures are local
estimates (characters / CHARS_PER_TOKEN); per-step output is an assumption, printed as one.
"""

import argparse
import json
import math
from datetime import date
from pathlib import Path

from ch14.golden import CountFact, resolve_count
from ch14.pricing import cost_of, load_price
from ch14.prompts import build_system_prompt
from ch14.settings import Settings
from ch14.tools import (
    READ_FILE_MAX_CHARS,
    SEARCH_MAX_RESULTS,
    SNIPPET_MAX_CHARS,
    TITLE_MAX_CHARS,
    URL_MAX_CHARS,
    CountRowsResult,
    SearchResult,
    build_registry,
)

OUTPUT_PER_STEP = 500  # assumption: tokens the model writes per step, including the answer


class NoSearch:  # design_check never searches
    def search(self, query: str, max_results: int, timeout_s: float) -> list[SearchResult]:
        return []


def last_full_quarter(today: date) -> tuple[date, date]:
    """[start, end) of the last full calendar quarter before `today`."""
    start_month = 3 * ((today.month - 1) // 3) + 1  # first month of today's quarter
    end = date(today.year, start_month, 1)
    month = start_month - 3
    start = date(today.year, month, 1) if month > 0 else date(today.year - 1, month + 12, 1)
    return start, end


def quarter_rows(path: Path, start: date, end: date) -> tuple[int, int, int, int]:
    """(rows in file, chars in file, rows in the quarter, chars of those rows)."""
    rows = chars = q_rows = q_chars = 0
    with path.open(encoding="utf-8") as f:
        header = f.readline().split(",")
        col = header.index("shipped_at")
        chars += len(f"{','.join(header)}")
        for line in f:
            rows += 1
            chars += len(line)
            if start <= date.fromisoformat(line.split(",")[col][:10]) < end:
                q_rows += 1
                q_chars += len(line)
    return rows, chars, q_rows, q_chars


def tokens(chars: int, settings: Settings) -> int:
    return math.ceil(chars / settings.chars_per_token)


def max_search_chars(results: int) -> int:
    worst = SearchResult(
        title="t" * TITLE_MAX_CHARS, url="u" * URL_MAX_CHARS, snippet="s" * SNIPPET_MAX_CHARS
    )
    return len(json.dumps([worst.model_dump()] * results))


def walk(plan: list[str], results: dict[str, int], fixed: int) -> tuple[int, int]:
    """Input and output tokens for a run of these steps: each call resends all before it."""
    history = total_in = 0
    for step in plan:
        total_in += fixed + history
        history += OUTPUT_PER_STEP + results[step]
    return total_in, OUTPUT_PER_STEP * len(plan)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--today", type=date.fromisoformat, required=True)
    parser.add_argument("--models", type=Path, default=Path("models.toml"))  # Chapter 11
    parser.add_argument("--config", default="hosted-sdk")
    args = parser.parse_args()
    s = Settings.from_env()

    print("1. Can the model read a quarter of shipments?")
    start, end = last_full_quarter(args.today)
    rows, chars, q_rows, q_chars = quarter_rows(s.exports_dir / "shipments.csv", start, end)
    pages = math.ceil(q_chars / READ_FILE_MAX_CHARS)
    print(f"   shipments.csv: {rows:,} rows, {chars:,} chars")
    print(f"   last quarter ({start} to {end}, by shipped_at): {q_rows:,} rows, {q_chars:,} chars")
    print(f"   = {pages} read_file pages of {READ_FILE_MAX_CHARS:,} chars")

    print("2. Fixed part of every call (local estimate)")
    system = build_system_prompt(args.today, s.prompt_version)
    registry = build_registry(
        s.exports_dir, NoSearch(), lambda: s.search_timeout_s, s.tool_result_max_chars
    )
    tools_chars = sum(len(json.dumps(d.model_dump())) for d in registry.definitions())
    fixed = tokens(len(system) + tools_chars, s)
    print(f"   system prompt: {len(system):,} chars, tool definitions: {tools_chars:,} chars")
    print(f"   = about {fixed:,} tokens per call")
    for n in (5, SEARCH_MAX_RESULTS):
        size = max_search_chars(n)
        verdict = "fits" if size <= s.tool_result_max_chars else "OVER"
        cap = s.tool_result_max_chars
        print(f"   {n} search results at their caps: {size:,} chars ({verdict} under {cap:,})")

    print(f"3. Carrier question walk-through (assumes {OUTPUT_PER_STEP} output tokens per step)")
    fact = CountFact(
        file="shipments.csv", where={"late": "yes"}, date_column="shipped_at",
        date_from=start, date_to=end, group_by="carrier",
    )  # fmt: skip
    groups = dict(resolve_count(fact, s.exports_dir))
    count = CountRowsResult(
        path="shipments.csv", rows_in_file=rows, rows_in_period=q_rows,
        rows_matched=sum(groups.values()), by_group=groups,
    )  # fmt: skip
    results = {
        "count_rows by carrier": tokens(len(count.model_dump_json()), s),
        "search_web x2, in parallel": 2 * tokens(max_search_chars(5), s),
        "final answer": 0,
        "final answer fails validation": tokens(300, s),  # the error message sent back
        "read_file, one page": tokens(READ_FILE_MAX_CHARS, s),
        "a tool error, corrected": tokens(300, s),
    }
    count_and_search = ["count_rows by carrier", "search_web x2, in parallel"]
    with_retry = [*count_and_search, "final answer fails validation", "final answer"]
    worse = ["read_file, one page", "a tool error, corrected", *with_retry]
    for name, plan in (
        ("happy path", [*count_and_search, "final answer"]),
        ("with a retry", with_retry),
        ("with a page read, an error and a retry", worse),
    ):
        total_in, total_out = walk(plan, results, fixed)
        total = total_in + total_out
        print(f"   {name}: {len(plan)} steps, {total_in:,} in + {total_out:,} out = {total:,}")
    print(f"   budget: {s.run_max_steps} steps, {s.run_max_tokens:,} tokens")

    print("4. Money for the worse run")
    price = load_price(args.models, args.config) if args.models.exists() else None
    if price is None or s.search_usd_per_query is None:
        print(f"   needs a priced {args.config!r} in {args.models} and SEARCH_USD_PER_QUERY")
        return
    cost = cost_of(total_in, total_out, price) + 2 * s.search_usd_per_query
    print(f"   about ${cost:.4f} per run (prices as of {price.as_of});")
    print(f"   RUN_MAX_COST_USD is ${s.run_max_cost_usd}")


if __name__ == "__main__":
    main()
