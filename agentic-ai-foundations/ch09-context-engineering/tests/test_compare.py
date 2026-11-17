"""The handbook comparison and the grader, on scripted fake-model runs."""

from pathlib import Path

import pytest
from ch09.grade import is_correct, quotes_stale
from ch09.handbook_compare import compare, grow_folder, render_handbook
from ch09.questions import QUESTIONS
from ch09.scripted import FAKE_BUDGET, FAKE_CONTEXT, FAKE_LIMITS, handbook_clients
from kestrel.workspace import copy_docs

TRADE = QUESTIONS[0]


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    copy_docs(tmp_path / "docs")
    return tmp_path / "docs"


def test_the_handbook_tags_every_doc_with_its_path(docs):
    text = render_handbook(docs)
    assert text.count("<doc path=") == 4 and '<doc path="shipping-policy.md">' in text


def test_variant_a_takes_one_step_and_variant_b_reads_the_expected_doc(docs):
    rows = compare(*handbook_clients(QUESTIONS), docs, QUESTIONS,
                   FAKE_BUDGET, FAKE_LIMITS, FAKE_CONTEXT)  # fmt: skip
    a_rows, b_rows = rows[0::2], rows[1::2]
    assert all(r.steps == 1 for r in a_rows) and all(r.steps == 3 for r in b_rows)
    for q, b in zip(QUESTIONS, b_rows, strict=True):
        assert b.read_paths == {q.expected_path}
    # At this handbook's size, sending all of it costs less than three tool steps.
    assert all(a.input_tokens < b.input_tokens for a, b in zip(a_rows, b_rows, strict=True))


def test_a_correct_answer_names_the_path_and_the_facts():
    answer = "The promise is 3 working days; late means delivered after its promised date.\n" \
        "Source: shipping-policy.md"  # fmt: skip
    assert is_correct(TRADE, answer) and is_correct(TRADE, answer, {"shipping-policy.md"})


def test_naming_a_path_the_run_never_read_is_not_correct():
    answer = "3 working days, late after its promised date. Source: shipping-policy.md"
    assert not is_correct(TRADE, answer, read_paths=set())


def test_relying_on_the_retired_page_is_caught_but_naming_it_is_not():
    assert quotes_stale(TRADE, "Standard delivery takes 4 working days.")
    assert not quotes_stale(TRADE, "shipping-policy-v2-OUTDATED.md is superseded; ignore it.")


def test_only_variant_a_sends_the_retired_pages_wording(docs):
    rows = compare(*handbook_clients(QUESTIONS), docs, QUESTIONS,
                   FAKE_BUDGET, FAKE_LIMITS, FAKE_CONTEXT)  # fmt: skip
    a, b = rows[0], rows[1]  # the trade question, which has a retired answer
    assert (a.stale_sent, b.stale_sent) == (True, False)
    assert rows[2].stale_sent is None  # no retired page to check for this question


def test_a_growing_folder_flips_the_cheaper_design(docs, tmp_path):
    question = QUESTIONS[:1]
    big = grow_folder(docs, tmp_path / "grown", extra=8)
    a, b = compare(*handbook_clients(question), big, question,
                   FAKE_BUDGET, FAKE_LIMITS, FAKE_CONTEXT)  # fmt: skip
    assert a.input_tokens > b.input_tokens  # small folder: A cheaper; eight more pages: B
