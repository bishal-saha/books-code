"""The batch end to end with the scripted fake model and the seeded mock API."""

import sys

import pytest
from ch05 import run
from ch05.fake_model import FakeModelClient
from ch05.model_client import ModelError
from ch05.sample_replies import VALID_JSON


def test_demo_report(kestrel_url: str, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("KESTREL_URL", kestrel_url)
    monkeypatch.setattr(sys, "argv", ["ch05.run", "--demo"])
    run.main()
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].split()[:2] == ["claim-01", "meals"] and lines[1].endswith("OVER_LIMIT")
    assert lines[3].split()[0] == "claim-04" and lines[3].split()[5] == "2"  # retried once
    assert lines[6].endswith("software   240.00 USD  yes      1         -")
    assert lines[7] == "claim-07  FAILED: invalid after 3 attempt(s)"
    assert lines[8].startswith("10 model calls")


def test_an_outage_prints_the_partial_report_and_exits_1(
    kestrel_url: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    outage = ModelError("provider_error", "the provider returned an error")
    monkeypatch.setattr(run, "demo_client", lambda: FakeModelClient([VALID_JSON, outage]))
    monkeypatch.setenv("KESTREL_URL", kestrel_url)
    monkeypatch.setattr(sys, "argv", ["ch05.run", "--demo"])
    with pytest.raises(SystemExit) as exc_info:
        run.main()
    assert str(exc_info.value) == "error: claim-02: the provider returned an error (provider_error)"
    assert capsys.readouterr().out.splitlines()[-1].startswith("1 model calls")
