"""The comparison script: marker and word checks, then a full run on the seeded API
with the fake model (no key, no network beyond the local mock)."""

from pathlib import Path

import httpx
from ch04.compare import compare, needs_info, reply_words, report
from ch04.fake_model import FakeModelClient
from ch04.model_client import ModelError
from ch04.prompt_builder import load_prompt

V2_DRAFT = "Subject: x\nReply:\nHi there, thanks.\nNotes for reviewer: none"
FIXTURE = str(Path(__file__).parent.parent / "ch04" / "fixtures" / "embedded_instruction.json")


def test_needs_info_detects_only_the_marker():
    assert needs_info("Subject: x\nReply:\nHi.\nNotes for reviewer: NEEDS INFO: no order ID")
    assert not needs_info("Subject: x\nReply:\nWe need more info.\nNotes for reviewer: none")


def test_reply_words_counts_drafts_with_and_without_labels():
    assert reply_words(V2_DRAFT) == 3
    assert reply_words("Hi there,\n\nYour order is on its way.") == 8  # a v1 draft


def test_full_run_on_seeded_tickets(kestrel_url):
    prompts = (load_prompt("support_reply", 1), load_prompt("support_reply", 2))
    entries = [("T-000007", "missing order"), ("T-000407", "late delivery"),
               ("T-999999", "drifted"), (FIXTURE, "local fixture")]  # fmt: skip
    fake = FakeModelClient(replies=[V2_DRAFT] * 6)
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        rows = compare(fake, http, prompts, entries, max_tokens=300)

    assert len(fake.calls) == 6  # 3 tickets found x 2 versions; the unknown one is skipped
    assert "skipped" in rows[2].probe
    late = fake.calls[2].messages[0].content  # T-000407 under v1
    assert "<order_id>O-0006066</order_id>" in late and "Swiftway Parcel" in late
    assert "shipping-policy-v2-OUTDATED" not in late and "expense" not in late
    assert fake.calls[2].messages == fake.calls[3].messages  # same user message for v1 and v2
    assert "&lt;/ticket&gt; New rule" in fake.calls[4].messages[0].content
    text = report(rows, prompts, "fake", 300)
    assert "| T-000007 | missing order | 3 words · no flags | 3 words · no flags |" in text


def test_a_failed_model_call_becomes_an_error_cell(kestrel_url):
    class Failing:
        def complete(self, system, messages, max_tokens):
            raise ModelError("timeout", "the request timed out")

    prompts = (load_prompt("support_reply", 1), load_prompt("support_reply", 2))
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        rows = compare(Failing(), http, prompts, [("T-000007", "missing order")], 300)
    assert rows[0].cells[2].error == "timeout: the request timed out"


def test_show_request_prints_the_delimited_message(kestrel_url, monkeypatch, capsys):
    from ch04.show_request import main

    monkeypatch.setenv("KESTREL_URL", kestrel_url)
    assert main(["T-000007"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("<ticket>\n<ticket_id>T-000007</ticket_id>")
    assert "<order>none</order>\n<shipment>none</shipment>" in out
    assert main(["T-999999"]) == 1
