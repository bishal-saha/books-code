"""The edges demo against the seeded mock API: fake model, real tool calls."""

from ch12 import edges


def test_edges_output(kestrel_url, monkeypatch, capsys):
    monkeypatch.setenv("KESTREL_URL", kestrel_url)
    edges.main()
    out = capsys.readouterr().out
    assert "track_parcel (1 ERR)" in out
    assert "stopped: finished  steps 3/3" in out
    assert "tool result: is_error=True Unknown tool: track_parcel." in out
    assert "stopped: step_limit  steps 3/3" in out
    assert "create_return_authorisation" not in out  # read-only reach
    assert "(partial result, labelled step_limit)" in out
