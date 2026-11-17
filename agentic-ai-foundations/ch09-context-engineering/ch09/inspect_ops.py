"""Chapter 8's operations agent (v2 tools) with the context inspector switched on.

uv run python -m ch09.inspect_ops --fake chased      # fake model, real Kestrel API, no key
uv run --env-file .env python -m ch09.inspect_ops O-0014614 O-0004943 O-0004365 O-9999999
"""

import argparse
import os
from datetime import date
from tempfile import TemporaryDirectory

from ch09.agent import print_steps, run_agent
from ch09.budget import CallLimits, RunBudget
from ch09.context_budget import ContextBudget, context_budget_from
from ch09.inspector import ContextInspector, context_table
from ch09.lookups import kestrel_client
from ch09.model_client import ModelClient
from ch09.prompts import load_prompt
from ch09.return_store import ReturnStore
from ch09.settings import DEFAULT_KESTREL_URL, Settings
from ch09.tools import build_registry

TODAY = date(2025, 12, 16)  # the fixed date the book's examples use


def question_for(order_ids: list[str]) -> str:
    return (
        f"A trade customer has chased these orders: {', '.join(order_ids)}. "
        "Where does each one stand, and which need a carrier trace?"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the operations agent with the inspector.")
    parser.add_argument("order_ids", nargs="*", help="order IDs for a live run")
    parser.add_argument("--fake", choices=["chased", "stuck"], help="scripted fake model")
    args = parser.parse_args()

    client: ModelClient
    context: ContextBudget
    if args.fake:
        from ch09.scripted import CHASED, FAKE_BUDGET, FAKE_CONTEXT, FAKE_LIMITS, SCENARIOS

        client, order_ids = SCENARIOS[args.fake](), CHASED
        budget, limits, context = FAKE_BUDGET, FAKE_LIMITS, FAKE_CONTEXT
        kestrel_url = os.environ.get("KESTREL_URL", DEFAULT_KESTREL_URL)
        print("[fake model: scripted replies; tool results from the mock API]")
    else:
        if not args.order_ids:
            parser.error("give order IDs, or --fake chased|stuck")
        from ch09.anthropic_adapter import AnthropicAdapter

        settings = Settings.from_env()
        if settings.api_key is None:
            raise SystemExit("error: set ANTHROPIC_API_KEY in .env (or use --fake)")
        client, order_ids = AnthropicAdapter(settings), args.order_ids
        budget = RunBudget(settings.run_max_steps, settings.run_max_tokens,
                           settings.run_max_seconds)  # fmt: skip
        limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
        context, kestrel_url = context_budget_from(settings), settings.kestrel_url

    system = load_prompt("ops_agent", 2).body
    inspector = ContextInspector(client, context)
    with kestrel_client(kestrel_url) as http, TemporaryDirectory() as tmp:
        store = ReturnStore(f"{tmp}/returns.sqlite")  # the write tool's store; unused here
        registry = build_registry(http, store, TODAY, context.tool_result_max_chars)
        result = run_agent(client, system, question_for(order_ids), registry, budget, limits,
                           inspector=inspector)  # fmt: skip
    print_steps(result, budget)
    print("\n".join(context_table([s.context for s in result.steps if s.context])))


if __name__ == "__main__":
    main()
