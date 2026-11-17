"""Regenerate the two sample traces in fixtures/traces/ (fake-model runs, real tool results).

uv run python -m ch13.sample_traces      # needs `uv run kestrel up`

wrong_carrier.jsonl: the capped-count guess the chapter reads. wrong_stock.jsonl: Exercise 2.
"""

from pathlib import Path

import httpx

from ch13.agent import run_agent
from ch13.budget import CallLimits, RunBudget
from ch13.fake_model import FakeModelClient
from ch13.kestrel_tools import build_ops_registry
from ch13.model_client import ModelResponse
from ch13.prompts import load_prompt
from ch13.scripted import ILLUSTRATIVE, failing_script, wrong_stock_script
from ch13.settings import Settings
from ch13.trace import TraceRecorder

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "traces"

SAMPLES: dict[str, tuple[str, str, int]] = {  # file -> (task id, question, max steps)
    "wrong_carrier": (
        "late-top-carrier-needs-info",
        "Which carrier has the most late shipments overall, and how many? "
        "Answer as JSON with carrier and late_shipments.",
        6,
    ),
    "wrong_stock": (
        "stock-total",
        "How many units of SKU-00042 are on hand across both warehouses? "
        "Answer as JSON with sku and total_on_hand.",
        4,
    ),
}


def record_sample(
    path: Path, task_id: str, question: str, max_steps: int, script: list[ModelResponse], http
) -> None:
    settings = Settings()
    prompt = load_prompt("operations", 1)
    budget = RunBudget(max_steps, settings.run_max_tokens, settings.run_max_seconds)
    limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
    registry = build_ops_registry(http, settings.tool_result_max_chars)
    with TraceRecorder(path, ILLUSTRATIVE) as recorder:
        recorder.run_start(path.stem, task_id, "operations_v1", "fake", budget)
        run_agent(
            FakeModelClient(script),
            prompt.body,
            question,
            registry,
            budget,
            limits,
            recorder=recorder,
        )


def main() -> None:
    scripts = {
        "wrong_carrier": failing_script("late-top-carrier-needs-info"),
        "wrong_stock": wrong_stock_script(),
    }
    with httpx.Client(base_url=Settings.from_env().kestrel_url, timeout=10.0) as http:
        for name, (task_id, question, max_steps) in SAMPLES.items():
            path = FIXTURES / f"{name}.jsonl"
            path.unlink(missing_ok=True)  # the recorder refuses to append to an old trace
            script = scripts[name]
            assert script is not None
            record_sample(path, task_id, question, max_steps, script, http)
            print(f"wrote {path.relative_to(FIXTURES.parent.parent)}")


if __name__ == "__main__":
    main()
