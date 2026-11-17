"""summarise_result: origin kept, usage returned, a fallback instead of a failure."""

from datetime import UTC, datetime

from ch09.fake_model import FakeModelClient
from ch09.model_client import ModelError, ModelResponse, Usage
from ch09.summarise import summarise_result

TEXT = "Policy text. " * 1_000  # 13,000 characters
WHEN = datetime(2026, 11, 16, tzinfo=UTC)
ARGS = dict(origin="https://example.com/p", kind="url", max_chars=2_000,
            max_input_chars=50_000, max_tokens=300, timeout=10.0, fetched_at=WHEN)  # fmt: skip


def test_a_summary_keeps_origin_and_fetched_at_and_is_flagged():
    fake = FakeModelClient(["A short summary."])
    result, usage = summarise_result(fake, TEXT, **ARGS)
    assert (result.origin, result.fetched_at, result.summarised) == (ARGS["origin"], WHEN, True)
    assert result.shown == [(0, len(TEXT))] and usage is not None
    assert fake.calls[0].timeout == 10.0  # the run's remaining time, passed through


def test_a_failed_call_falls_back_to_a_capped_result():
    result, usage = summarise_result(FakeModelClient([ModelError("timeout", "slow")]), TEXT, **ARGS)
    assert (result.summarised, result.truncated, usage) == (False, True, None)
    assert result.origin == ARGS["origin"]


def test_a_cut_off_summary_falls_back_but_reports_its_usage():
    cut = ModelResponse(text="A partial", stop_reason="truncated",
                        usage=Usage(input_tokens=3_300, output_tokens=300))  # fmt: skip
    result, usage = summarise_result(FakeModelClient([cut]), TEXT, **ARGS)
    assert not result.summarised and usage == cut.usage


def test_text_too_large_to_summarise_is_capped_without_a_call():
    fake = FakeModelClient([])
    result, usage = summarise_result(fake, TEXT, **{**ARGS, "max_input_chars": 1_000})
    assert fake.calls == [] and usage is None and result.truncated


def test_a_complete_summary_over_the_cap_falls_back():
    result, usage = summarise_result(FakeModelClient(["word " * 600]), TEXT, **ARGS)
    assert not result.summarised and result.truncated and usage is not None
