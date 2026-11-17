"""Final-answer checking: shape first (Chapter 5), then every citation against the run."""

import json

from ch16.final import check_final, retry_message
from ch16.scripted import fixture_answer

RETURNED = {
    "shipments.csv",
    "https://reviews.example.com/harbour-express",
    "https://reviews.example.com/swiftway-parcel",
}


def test_a_valid_answer_with_returned_citations_is_accepted() -> None:
    check = check_final(json.dumps(fixture_answer("carriers")), RETURNED)
    assert check.accepted and check.answer is not None


def test_fenced_json_is_accepted() -> None:
    text = "```json\n" + json.dumps(fixture_answer("needs_info")) + "\n```"
    assert check_final(text, set()).accepted


def test_prose_instead_of_json_fails_validation() -> None:
    check = check_final("Harbour Express was late most often.", RETURNED)
    assert check.answer is None and check.errors and not check.accepted


def test_a_rule_the_schema_enforces_is_reported_by_field() -> None:
    answer = fixture_answer("carriers") | {"confidence": "high"}  # two claims cite only URLs
    check = check_final(json.dumps(answer), RETURNED)
    assert check.answer is None
    assert check.errors == [
        "(root): Value error, high confidence needs a file citation on every claim"
    ]


def test_an_unreturned_url_is_named_with_its_index() -> None:
    check = check_final(json.dumps(fixture_answer("carriers")), {"shipments.csv"})
    assert check.answer is not None and not check.accepted
    assert [e.split(":")[0] for e in check.errors] == ["citations.1", "citations.2"]


def test_the_retry_message_lists_the_citable_set_as_data() -> None:
    check = check_final(json.dumps(fixture_answer("carriers")), {"shipments.csv"})
    message = retry_message(check, {"shipments.csv", "https://x.example.com/?a=1&b=<2>"})
    assert "<data>https://x.example.com/?a=1&amp;b=&lt;2&gt;\nshipments.csv</data>" in message
    assert message.startswith("Your final answer was rejected:\n- citations.1")
