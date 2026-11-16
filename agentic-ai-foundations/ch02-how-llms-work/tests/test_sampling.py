import pytest
from ch02.sampling_demo import QUESTION, run_demo
from ch02.tokens import load_page


def test_counts_variants_and_truncation_and_bills_every_run(settings, fake_client):
    client = fake_client(count=200, responses="sampling_responses.json")
    page = load_page(settings, "returns-policy.md")
    report = run_demo(client, settings, page, runs=5, max_tokens=256)

    assert report.runs == 5
    assert report.truncated == 1  # stopped at max_tokens: not a variant
    assert report.distinct == 2  # two wordings of the same fact
    assert all("30 days" in answer for answer in report.answers)
    assert report.cost.output_tokens == 16 + 20 + 16 + 8 + 16  # truncated run billed too
    assert report.cost.input_tokens == 5 * 180


def test_sends_the_same_request_every_time(settings, fake_client):
    client = fake_client(count=200, responses="sampling_responses.json")
    run_demo(client, settings, load_page(settings, "returns-policy.md"), runs=5, max_tokens=256)
    assert len(client.requests) == 5
    assert all(r == client.requests[0] for r in client.requests)
    assert QUESTION in client.requests[0]["messages"][0]["content"]


def test_refuses_a_prompt_that_does_not_fit(settings, fake_client):
    client = fake_client(count=9_900, responses="sampling_responses.json")
    with pytest.raises(ValueError, match="does not fit"):
        run_demo(client, settings, "page", runs=5, max_tokens=256)
    assert client.requests == []  # nothing was sent, nothing was billed
