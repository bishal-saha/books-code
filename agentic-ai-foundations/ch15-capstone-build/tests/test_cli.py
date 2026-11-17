"""The command line: what it prints for each outcome, its exit codes, and the trace it writes."""

from pathlib import Path

import pytest
from ch15.cli import EXIT_ANSWERED, EXIT_NEEDS_INFO, EXIT_REJECTED, EXIT_STOPPED, EXIT_USAGE, main
from ch15.trace import read_trace


def cli(argv: list[str], exports: Path, tmp_path: Path, **env: str) -> tuple[int, list[str]]:
    lines: list[str] = []
    env = {"EXPORTS_DIR": str(exports), **env}
    code = main([*argv, "--traces", str(tmp_path / "traces")], env, lines.append)
    return code, lines


@pytest.mark.parametrize(
    ("demo", "code", "first"),
    [
        ("carriers-late-last-quarter", EXIT_ANSWERED, "ANSWERED  (confidence: medium)"),
        ("quarter-not-covered", EXIT_NEEDS_INFO, "NEEDS INFO  (confidence: low)"),
        ("invented-url-rejected", EXIT_REJECTED, "REJECTED: the final answer failed"),
        ("never-stops", EXIT_STOPPED, "STOPPED: step_limit. No answer"),
    ],
)
def test_each_outcome_prints_and_exits(demo, code, first, exports, tmp_path) -> None:
    exit_code, lines = cli(["--demo", demo], exports, tmp_path)
    assert exit_code == code
    assert lines[0].startswith("[demo ")  # fake-model output is always labelled
    assert any(line.startswith(first) for line in lines)


def test_the_trace_ends_with_outcome_citable_set_and_cost(exports, tmp_path) -> None:
    cli(["--demo", "invented-url-corrected"], exports, tmp_path)
    (path,) = (tmp_path / "traces").glob("*.jsonl")
    events = read_trace(path)
    checks = [e for e in events if e["kind"] == "final_check"]
    assert [c["accepted"] for c in checks] == [False, True]
    end = events[-1]
    assert end["kind"] == "run_end" and end["outcome"] == "answered"
    assert "shipments.csv" in end["citable"] and end["model_usd"] == "0.0150"


def test_startup_problems_are_one_line_and_exit_2(exports, tmp_path) -> None:
    code, lines = cli(["question?", "--models", str(tmp_path / "none.toml")], exports, tmp_path)
    expected = f"error: {tmp_path / 'none.toml'} not found: copy models.example.toml and fill it in"
    assert code == EXIT_USAGE and lines == [expected]
    code, lines = cli(["--demo", "sandbox-probe"], tmp_path / "missing", tmp_path)
    assert code == EXIT_USAGE and "uv run kestrel up --no-serve" in lines[0]
    code, lines = cli(["--demo", "sandbox-probe"], exports, tmp_path, RUN_MAX_STEPS="0")
    assert code == EXIT_USAGE and lines[0].startswith("error: run_max_steps:")


def test_a_live_configuration_without_its_key_never_starts(exports, tmp_path) -> None:
    models = tmp_path / "models.toml"
    models.write_text(
        '[[config]]\nname = "hosted-sdk"\nprovider = "anthropic"\n'
        'model_env = "MODEL"\napi_key_env = "ANTHROPIC_API_KEY"\n'
    )
    code, lines = cli(["question?", "--models", str(models)], exports, tmp_path)
    assert code == EXIT_USAGE
    assert lines == ["error: not configured (MODEL, ANTHROPIC_API_KEY empty)"]
