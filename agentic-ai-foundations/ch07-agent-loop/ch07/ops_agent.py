"""The operations agent: run_agent over three read-only Kestrel tools.

uv run --env-file .env python -m ch07.ops_agent O-0014614 O-0004943 O-0004365 O-9999999
uv run python -m ch07.ops_agent --fake chased   # fake model, real Kestrel API, no key
uv run python -m ch07.ops_agent --fake stuck    # a fake model that never stops on its own
"""

import argparse
import os

import httpx

from ch07.agent import print_steps, run_agent
from ch07.budget import CallLimits, RunBudget
from ch07.model_client import ModelClient
from ch07.prompts import load_prompt
from ch07.settings import DEFAULT_KESTREL_URL, Settings
from ch07.tools import build_registry

FAKE_BUDGET = RunBudget(max_steps=8, max_total_tokens=60_000, max_wall_seconds=90.0)
FAKE_LIMITS = CallLimits(max_output_tokens=1024, timeout_seconds=30.0)  # Settings defaults


def question_for(order_ids: list[str]) -> str:
    return (
        f"A trade customer has chased these orders: {', '.join(order_ids)}. "
        "Where does each one stand, and which need a carrier trace?"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate chased orders and late shipments.")
    parser.add_argument("order_ids", nargs="*", help="order IDs for a live run")
    parser.add_argument("--fake", choices=["chased", "stuck"], help="scripted fake model")
    args = parser.parse_args()

    client: ModelClient
    if args.fake:
        from ch07.scripted import CHASED, SCENARIOS

        client, order_ids = SCENARIOS[args.fake](), CHASED
        budget, limits = FAKE_BUDGET, FAKE_LIMITS
        kestrel_url = os.environ.get("KESTREL_URL", DEFAULT_KESTREL_URL)
        print("[fake model: scripted replies and token counts; tool results from Kestrel]")
    else:
        if not args.order_ids:
            parser.error("give order IDs, or --fake chased|stuck")
        from ch07.anthropic_adapter import AnthropicAdapter

        settings = Settings.from_env()
        if settings.api_key is None:
            raise SystemExit("error: set ANTHROPIC_API_KEY in .env (or use --fake)")
        client, order_ids = AnthropicAdapter(settings), args.order_ids
        budget = RunBudget(
            max_steps=settings.run_max_steps,
            max_total_tokens=settings.run_max_tokens,
            max_wall_seconds=settings.run_max_seconds,
        )
        limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
        kestrel_url = settings.kestrel_url

    system = load_prompt("ops_agent", 1).body
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:  # tool calls: 5 s each
        result = run_agent(client, system, question_for(order_ids), build_registry(http),
                           budget, limits)  # fmt: skip
    print_steps(result, budget)
    print(result.final_text)


if __name__ == "__main__":
    main()
