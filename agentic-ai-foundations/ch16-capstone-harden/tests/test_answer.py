"""FinalAnswer's validators: what code rejects before anyone reads the answer."""

import json
from pathlib import Path

import pytest
from ch16.answer import FinalAnswer
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "answers"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_fixtures_validate() -> None:
    assert FinalAnswer.model_validate(load("carriers.json")).status == "answered"
    assert FinalAnswer.model_validate(load("needs_info.json")).status == "needs_info"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda a: a.update(claims=[]), "at least one claim"),
        (lambda a: a["claims"][0].update(citations=[7]), "index that doesn't exist"),
        (lambda a: a["claims"][0].update(citations=[]), "at least 1 item"),
        (lambda a: a.update(confidence="high"), "file citation on every claim"),
        (lambda a: a["citations"][0].update(location="/srv/exports/shipments.csv"), "relative"),
        (lambda a: a["citations"][0].update(location="../kestrel.sqlite"), "relative"),
        (lambda a: a["citations"][1].update(location="reviews.example.com"), "http"),
    ],
)  # fmt: skip
def test_answered_rules(change, message: str) -> None:
    answer = load("carriers.json")
    change(answer)
    with pytest.raises(ValidationError, match=message):
        FinalAnswer.model_validate(answer)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda a: a.update(answer="There were no late deliveries."), "NEEDS INFO"),
        (lambda a: a.update(missing=[]), "lists what is missing"),
        (lambda a: a.update(answer="NEEDS INFO: " + "x" * 300), "under 300"),
    ],
)
def test_needs_info_rules(change, message: str) -> None:
    answer = load("needs_info.json")
    change(answer)
    with pytest.raises(ValidationError, match=message):
        FinalAnswer.model_validate(answer)


def test_partial_answer_keeps_what_is_missing() -> None:
    """Counts found, public view not: an answer that says what it couldn't cover."""
    answer = load("carriers.json")
    answer["claims"] = answer["claims"][:1]
    answer["citations"] = answer["citations"][:1]
    answer["confidence"] = "high"  # every remaining claim rests on a file
    answer["missing"] = ["public sources about Harbour Express or Swiftway Parcel"]
    assert FinalAnswer.model_validate(answer).missing
