"""The money budget, the per-call timeout, and what a stopped run reports. Fake model only."""

from decimal import Decimal
from pathlib import Path

from ch16.budget import StopCause
from ch16.cli import EXIT_STOPPED, EXIT_USAGE, main
from ch16.fake_model import FakeModelClient
from ch16.golden import load_golden_tasks
from ch16.offline import OfflineSearchService
from ch16.research import run_research
from ch16.scripted import ILLUSTRATIVE, ILLUSTRATIVE_SEARCH_USD, carriers, key_rejected
from ch16.settings import Settings

TASK = next(t for t in load_golden_tasks() if t.id == "carriers-late-last-quarter")


def research(exports: Path, script, max_cost: str = "0.50", clock=None, **settings):
    s = Settings(
        exports_dir=exports,
        search_usd_per_query=ILLUSTRATIVE_SEARCH_USD,
        run_max_cost_usd=Decimal(max_cost),
        **settings,
    )
    client = FakeModelClient(script)
    extra = {"clock": clock} if clock else {}
    backend = OfflineSearchService().backend()
    result = run_research(
        TASK.input, TASK.today, s, client, backend, ILLUSTRATIVE, sleep=lambda x: None, **extra
    )
    return result, client


def test_cost_limit_stops_before_the_call_it_cannot_afford(exports: Path) -> None:
    # Illustrative prices: $1 in, $5 out per million tokens; $0.005 per search request.
    # Steps 1 and 2: 2,400 in + 80 out each = $0.0028 each; two searches = $0.0100.
    # Spent before step 3: $0.0156 of $0.0160. The input alone would cost more than $0.0004.
    result, client = research(exports, carriers(), max_cost="0.016")
    assert result.run.cause is StopCause.COST_LIMIT and result.outcome == "stopped"
    assert len(client.calls) == 2  # the third call was never sent
    assert (result.model_usd, result.search_usd) == (Decimal("0.0056"), Decimal("0.010"))
    assert result.run.stop_detail.startswith("money budget: $0.0156 of $0.0160 spent")
    assert "shipments.csv" in result.gathered  # unchecked, never printed as an answer


def test_the_output_cap_shrinks_to_what_money_can_pay(exports: Path) -> None:
    result, client = research(exports, carriers(), max_cost="0.021")
    assert result.outcome == "answered"
    assert 256 <= client.calls[2].max_tokens < 1024  # step 3 got a smaller cap, not a stop


def test_the_overshoot_is_at_most_one_call(exports: Path) -> None:
    # The fake model reports 3,200 input tokens for step 3; the loop estimated fewer from the
    # characters it sent, so the call costs more than the check allowed for. One call, no more.
    result, _ = research(exports, carriers(), max_cost="0.0196")
    spent = result.model_usd + result.search_usd
    last_call = Decimal("0.0047")  # 3,200 in + 300 out at the illustrative prices
    assert result.outcome == "answered" and spent > Decimal("0.0196")  # over, by one call
    assert spent - Decimal("0.0196") <= last_call


def test_a_budget_too_small_for_one_call_stops_with_nothing_gathered(exports: Path) -> None:
    result, client = research(exports, carriers(), max_cost="0.0005")
    assert result.run.cause is StopCause.COST_LIMIT and client.calls == []
    assert result.gathered == []


def test_a_permanent_model_error_says_who_must_act(exports: Path) -> None:
    result, _ = research(exports, key_rejected())
    assert result.run.cause is StopCause.MODEL_ERROR
    assert result.run.stop_detail.endswith("permanent (auth): the API key was rejected; "
                                           "fix the setup first")  # fmt: skip


def test_each_call_shares_the_time_left_with_the_sdk_retry(exports: Path) -> None:
    now = [0.0]
    result, client = research(
        exports, carriers(), clock=lambda: now[0], run_max_seconds=40.0, max_retries=1
    )
    assert client.calls[0].timeout == 20.0  # min(MODEL_TIMEOUT_S 30, 40 s left / 2 attempts)
    assert result.outcome == "answered"


def cli(argv: list[str], exports: Path, tmp_path: Path) -> tuple[int, list[str]]:
    lines: list[str] = []
    env = {"EXPORTS_DIR": str(exports)}
    return main([*argv, "--traces", str(tmp_path / "t")], env, lines.append), lines


def test_the_cli_names_the_limit_and_labels_the_partial(exports: Path, tmp_path: Path) -> None:
    code, lines = cli(["--demo", "carriers-tight-money"], exports, tmp_path)
    assert code == EXIT_STOPPED
    assert lines[5].startswith("STOPPED: cost_limit (money budget: $0.0156 of $0.0160 spent")
    assert lines[6].startswith("PARTIAL, unchecked: no answer was written.")
    assert "Cost: $0.0156 of the $0.0160 budget" in "\n".join(lines)


def test_an_unpriced_configuration_never_starts(exports: Path, tmp_path: Path) -> None:
    models = tmp_path / "models.toml"
    models.write_text(
        '[[config]]\nname = "local-server"\nprovider = "openai_compatible"\n'
        'model_env = "M"\napi_key_env = "K"\nbase_url_env = "U"\n'
    )
    code, lines = cli(
        ["q?", "--config", "local-server", "--models", str(models)], exports, tmp_path
    )
    assert code == EXIT_USAGE and "has no price, so RUN_MAX_COST_USD can't be enforced" in lines[0]
