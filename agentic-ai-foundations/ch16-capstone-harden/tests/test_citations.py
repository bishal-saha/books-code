"""Citation checking: only locations a tool returned in this run count."""

import json
from pathlib import Path

from ch16.answer import FinalAnswer
from ch16.citations import check_citations, citable_locations, normalise_url
from ch16.tools import CountRowsResult, SearchResult
from ch16.truncate import ProvenancedResult

ANSWER = FinalAnswer.model_validate_json(
    (Path(__file__).resolve().parent.parent / "fixtures/answers/carriers.json").read_text()
)
SEARCH = [
    SearchResult(title="t", url="https://Reviews.Example.com/harbour-express#top", snippet="s"),
    SearchResult(title="t", url="https://reviews.example.com/swiftway-parcel", snippet="s"),
]


def returned_in_run() -> set[str]:
    """What the registry would collect from this run's successful tool outputs."""
    count = CountRowsResult(
        path="shipments.csv", rows_in_file=1, rows_in_period=1, rows_matched=1, by_group={}
    )
    return (
        citable_locations("search_web", [r.model_dump() for r in SEARCH])
        | citable_locations("count_rows", count)
        | citable_locations("calculate", {"expression": "1+1", "value": "2"})
    )


def test_every_citation_was_returned() -> None:
    assert check_citations(ANSWER, returned_in_run()) == []


def test_a_remembered_url_fails() -> None:
    answer = ANSWER.model_copy(deep=True)
    answer.citations[2].location = "https://reviews.example.com/swiftway-parcel?page=2"
    errors = check_citations(answer, returned_in_run())
    assert [e.index for e in errors] == [2]  # a different query string is a different page


def test_a_guessed_file_fails() -> None:
    answer = ANSWER.model_copy(deep=True)
    answer.citations[0].location = "shipments_2025.csv"
    assert [e.location for e in check_citations(answer, returned_in_run())] == [
        "shipments_2025.csv"
    ]


def test_normalisation_is_small() -> None:
    assert normalise_url("HTTPS://Example.COM/A?x=1#frag") == "https://example.com/A?x=1"


def test_read_file_cites_its_origin() -> None:
    page = ProvenancedResult(
        origin="shipments.csv", kind="file", total_chars=10, shown=[(0, 10)], content="a"
    )
    assert citable_locations("read_file", page) == {"shipments.csv"}


def test_calculate_cites_nothing() -> None:
    assert citable_locations("calculate", json.loads('{"value": "2"}')) == set()


def test_a_dot_slash_file_name_matches() -> None:
    answer = ANSWER.model_copy(deep=True)
    answer.citations[0].location = "./shipments.csv"
    assert check_citations(answer, returned_in_run()) == []
