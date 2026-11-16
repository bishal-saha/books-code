from decimal import Decimal

import pytest
from ch03.draft_reply import run
from ch03.fake_model import FailMidStream, FakeModelClient, ScriptExhausted
from ch03.model_client import ModelError, ModelResponse, StopReason, Usage
from ch03.settings import Settings
from ch03.ticket_prompt import SYSTEM_PROMPT, fetch_ticket

TICKET = {"ticket_id": "T-000407", "subject": "Where is my order?", "messages": []}
# Test values only. Built directly, so no .env file or environment variable is read.
SETTINGS = Settings(
    model="fake", input_price_per_mtok=Decimal("2"), output_price_per_mtok=Decimal("10")
)


def reply(text: str, stop: StopReason = "finished") -> ModelResponse:
    usage = Usage(input_tokens=1_000, output_tokens=200)
    return ModelResponse(text=text, stop_reason=stop, usage=usage)


def test_streamed_draft_prints_text_and_footer(capsys):
    fake = FakeModelClient([reply("Thanks for your patience with order O-0006066.")], chunk_size=5)
    assert run(fake, SETTINGS, TICKET) == 0
    out = capsys.readouterr().out
    assert "Thanks for your patience with order O-0006066." in out  # chunks reassembled
    assert "stop: finished" in out
    assert "cost: $0.004000" in out  # 1,000 x $2/M + 200 x $10/M


@pytest.mark.parametrize("stop, label", [("truncated", "[truncated]"), ("other", "[stopped]")])
def test_unfinished_replies_are_labelled_not_crashed(capsys, stop, label):
    assert run(FakeModelClient([reply("Thanks for", stop)]), SETTINGS, TICKET) == 0
    assert label in capsys.readouterr().out


def test_timeout_gives_one_line_and_nonzero_exit(capsys):
    code = run(FakeModelClient([ModelError("timeout", "timed out")]), SETTINGS, TICKET)
    assert code == 1
    assert "timed out" in capsys.readouterr().err


def test_failure_after_some_text_marks_it_incomplete(capsys):
    fake = FakeModelClient(
        [FailMidStream("Thanks for", ModelError("provider_error", "stream dropped"))]
    )
    assert run(fake, SETTINGS, TICKET) == 1
    out = capsys.readouterr().out
    assert "Thanks for" in out
    assert "[incomplete]" in out
    assert "stop:" not in out  # no footer for a failed stream


def test_no_stream_uses_complete(capsys):
    assert run(FakeModelClient(["Hi."]), SETTINGS, TICKET, stream=False) == 0
    assert "Hi.\nstop: finished" in capsys.readouterr().out


def test_cli_sends_the_system_prompt_and_the_output_cap():
    fake = FakeModelClient([reply("Hi.")])
    run(fake, SETTINGS, TICKET)
    assert fake.calls[0].system == SYSTEM_PROMPT
    assert fake.calls[0].max_tokens == SETTINGS.max_output_tokens
    assert "Never promise a refund." in SYSTEM_PROMPT


def test_an_extra_call_fails_the_test():
    fake = FakeModelClient([])
    with pytest.raises(ScriptExhausted):
        fake.complete(SYSTEM_PROMPT, [], 10)


def test_a_seeded_ticket_reaches_the_model(kestrel_url):
    ticket = fetch_ticket(kestrel_url, "T-000407")  # Chapter 1's late-delivery ticket
    fake = FakeModelClient([reply("Hi.")])
    assert run(fake, SETTINGS, ticket) == 0
    assert "O-0006066" in fake.calls[0].messages[0].content
