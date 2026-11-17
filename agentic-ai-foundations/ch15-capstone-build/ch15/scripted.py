"""Fake-model scripts for the tests and `python -m ch15.cli --demo NAME`.

Everything the "model" says here is written by hand: tool calls, final answers and token
counts are fake-model output. Tool results are real: count_rows and read_file read the seeded
exports, and search_web reads the hand-written fixture (fixtures/search/carriers.json).
"""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from ch15.model_client import ModelResponse, ToolCall, Usage
from ch15.pricing import Price

FOLDER = Path(__file__).resolve().parent.parent
ILLUSTRATIVE = Price(
    input_per_mtok=Decimal("1.00"),
    output_per_mtok=Decimal("5.00"),
    as_of=date(2026, 11, 16),
    source_url="illustrative price for the fake model, not a real seller's",
)
_ids = itertools.count(1)


def tool_use(*calls: tuple[str, dict], input_tokens: int = 2_400, output_tokens: int = 80):
    """A scripted response asking for one or more tool calls (several: parallel calls)."""
    usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
    return ModelResponse(
        text="",
        stop_reason="tool_call",
        usage=usage,
        tool_calls=[ToolCall(id=f"call_fake_{next(_ids)}", name=n, arguments=a) for n, a in calls],
    )


def finished(answer: dict | str, *, input_tokens: int = 3_200, output_tokens: int = 300):
    """A scripted final message: the FinalAnswer JSON (or any text, to script a bad reply)."""
    text = answer if isinstance(answer, str) else json.dumps(answer, indent=1)
    usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
    return ModelResponse(text=text, stop_reason="finished", usage=usage)


def fixture_answer(name: str) -> dict:
    """A hand-written answer from fixtures/answers/ (Chapter 14), not model output."""
    return json.loads((FOLDER / "fixtures" / "answers" / f"{name}.json").read_text("utf-8"))


LATE_Q4 = {
    "path": "shipments.csv",
    "where": {"late": "yes"},
    "date_column": "shipped_at",
    "date_from": "2025-10-01",
    "date_to": "2026-01-01",
    "group_by": "carrier",
}
SEARCHES = (
    ("search_web", {"query": "Harbour Express delivery reviews"}),
    ("search_web", {"query": "Swiftway Parcel delivery reviews"}),
)
INVENTED = "https://reviews.example.com/harbour-express-complaints"  # no tool returns this


def carriers() -> list[ModelResponse]:
    return [
        tool_use(("count_rows", LATE_Q4)),
        tool_use(*SEARCHES),
        finished(fixture_answer("carriers")),
    ]


def with_invented_url() -> dict:
    answer = fixture_answer("carriers")
    answer["citations"][1]["location"] = INVENTED
    return answer


def invented_url_corrected() -> list[ModelResponse]:
    """Cites a URL no tool returned, then fixes it after the retry message."""
    return [*carriers()[:2], finished(with_invented_url()), finished(fixture_answer("carriers"))]


def invented_url_rejected() -> list[ModelResponse]:
    """Cites the same invented URL again after the retry: the run is rejected."""
    return [*carriers()[:2], finished(with_invented_url()), finished(with_invented_url())]


def no_search_partial() -> list[ModelResponse]:
    """search_web isn't configured: the counts are answered, the web half goes under missing."""
    return [
        tool_use(("count_rows", LATE_Q4)),
        tool_use(*SEARCHES),
        finished(
            {
                "status": "answered",
                "answer": "Harbour Express had the most late deliveries in Q4 2025 (139), then "
                "Swiftway Parcel (93). Public sources could not be searched.",
                "claims": [
                    {
                        "text": "In Q4 2025, Harbour Express had 139 late deliveries and "
                        "Swiftway Parcel 93, the two highest.",
                        "citations": [0],
                    }
                ],
                "citations": [
                    {
                        "kind": "file",
                        "location": "shipments.csv",
                        "supports": "late shipments per carrier, Q4 2025",
                    }
                ],
                "confidence": "high",
                "missing": ["what public sources say about the carriers: search_web unavailable"],
            }
        ),
    ]


def counted(where: dict, date_from: str, date_to: str, claim: str, summary: str):
    args = {"path": "shipments.csv", "where": where, "date_column": "shipped_at"}
    args |= {"date_from": date_from, "date_to": date_to}
    answer = {
        "status": "answered",
        "answer": summary,
        "claims": [{"text": claim, "citations": [0]}],
        "citations": [{"kind": "file", "location": "shipments.csv", "supports": claim}],
        "confidence": "high",
        "missing": [],
    }
    return [tool_use(("count_rows", args)), finished(answer)]


def lost_by_one_carrier() -> list[ModelResponse]:
    claim = "Tallpine Logistics lost 13 shipments shipped in 2025."
    where = {"carrier": "Tallpine Logistics", "status": "lost"}
    return counted(where, "2025-01-01", "2026-01-01", claim, claim)


def zero_in_a_covered_month() -> list[ModelResponse]:
    claim = "Northline Freight lost 0 shipments shipped in October 2025."
    where = {"carrier": "Northline Freight", "status": "lost"}
    return counted(where, "2025-10-01", "2025-11-01", claim, claim)


def quarter_not_covered() -> list[ModelResponse]:
    q2 = {**LATE_Q4, "date_from": "2026-04-01", "date_to": "2026-07-01"}
    return [tool_use(("count_rows", q2)), finished(fixture_answer("needs_info"))]


def sandbox_probe() -> list[ModelResponse]:
    refusal = {
        "status": "needs_info",
        "answer": "NEEDS INFO: the file sandbox refused ../kestrel.sqlite, and no tool can read "
        "the database's tables.",
        "claims": [],
        "citations": [],
        "confidence": "low",
        "missing": ["the tables in kestrel.sqlite, which is outside the sandboxed folder"],
    }
    return [tool_use(("read_file", {"path": "../kestrel.sqlite"})), finished(refusal)]


def never_stops() -> list[ModelResponse]:
    return [tool_use(("count_rows", LATE_Q4)) for _ in range(20)]


@dataclass(frozen=True)
class Demo:
    task_id: str  # the golden task whose question and date the demo uses
    script: Callable[[], list[ModelResponse]]
    search: Literal["fixture", "none"] = "fixture"


DEMOS = {
    "carriers-late-last-quarter": Demo("carriers-late-last-quarter", carriers),
    "lost-by-one-carrier": Demo("lost-by-one-carrier", lost_by_one_carrier),
    "zero-in-a-covered-month": Demo("zero-in-a-covered-month", zero_in_a_covered_month),
    "quarter-not-covered": Demo("quarter-not-covered", quarter_not_covered),
    "sandbox-probe": Demo("sandbox-probe", sandbox_probe),
    "invented-url-corrected": Demo("carriers-late-last-quarter", invented_url_corrected),
    "invented-url-rejected": Demo("carriers-late-last-quarter", invented_url_rejected),
    "no-search-partial": Demo("carriers-late-last-quarter", no_search_partial, "none"),
    "never-stops": Demo("carriers-late-last-quarter", never_stops),
}
