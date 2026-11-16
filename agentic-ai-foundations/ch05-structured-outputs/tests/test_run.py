"""The batch end to end with the scripted fake model and the seeded mock API."""

import sys

import pytest
from ch05 import run


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
