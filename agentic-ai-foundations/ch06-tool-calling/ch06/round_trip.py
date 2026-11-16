"""One tool-calling round trip, printed message by message.

uv run --env-file .env python -m ch06.round_trip "Is order O-0000141 still open?"
uv run python -m ch06.round_trip --fake single      # fake model, real Kestrel API, no key
uv run python -m ch06.round_trip --fake parallel
"""

import argparse
import json
import os
from collections.abc import Callable

import httpx

from ch06.model_client import (
    Message,
    ModelClient,
    ModelResponse,
    ToolChoice,
    assistant_message,
    tool_results_message,
)
from ch06.prompts import load_prompt
from ch06.settings import DEFAULT_KESTREL_URL
from ch06.tools import ToolRegistry, build_registry

MAX_TOKENS = 400  # the fake-model runs; live runs use MAX_OUTPUT_TOKENS from settings


def needs_tools(response: ModelResponse) -> bool:
    """Decide from the stop reason alone. True means: dispatch the tool calls."""
    match response.stop_reason:
        case "finished":
            return False
        case "tool_call":
            return True
        case "truncated":
            raise RuntimeError("Output was cut off; not running a possibly partial tool call.")
        case other:
            raise RuntimeError(f"Unexpected stop reason: {other}")


def print_response(response: ModelResponse, out: Callable[[str], None] = print) -> None:
    out(f"stop reason: {response.stop_reason}")
    if response.text:
        out(f"text: {response.text}")
    for call in response.tool_calls:
        out(f"tool call: {json.dumps(call.model_dump())}")


def run_round_trip(
    client: ModelClient,
    registry: ToolRegistry,
    system: str,
    question: str,
    max_tokens: int,
    first_choice: ToolChoice | None = None,
    followup_choice: ToolChoice | None = None,
    out: Callable[[str], None] = print,
) -> ModelResponse:
    """One model call, dispatch of its tool calls, one follow-up call. No repetition."""
    messages = [Message(role="user", content=question)]
    tools = registry.definitions()

    out(f"-- model call 1 (messages: {len(messages)})")
    first = client.complete(system, messages, max_tokens, tools, first_choice)
    print_response(first, out)
    if not needs_tools(first):
        return first  # answered without a tool: no round trip to make

    results = [registry.dispatch(call) for call in first.tool_calls]
    for r in results:
        out(f"result for {r.tool_call_id} (is_error={r.is_error}): {r.content}")
    messages.append(assistant_message(first))
    messages.append(tool_results_message(results))  # all results, one user message

    out(f"-- model call 2 (messages: {len(messages)})")
    second = client.complete(system, messages, max_tokens, tools, followup_choice)
    print_response(second, out)
    if needs_tools(second):
        out("The model asked for another tool. Repeating the cycle is Chapter 7's agent loop.")
    return second


def main() -> None:
    parser = argparse.ArgumentParser(description="One tool-calling round trip.")
    parser.add_argument("question", nargs="?", help="the question for a live run")
    parser.add_argument("--fake", choices=["single", "parallel"], help="scripted fake model")
    parser.add_argument("--wire", action="store_true", help="with --fake: print the messages")
    args = parser.parse_args()

    system = load_prompt("order_lookup", 1).body
    kestrel_url = os.environ.get("KESTREL_URL", DEFAULT_KESTREL_URL)
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as http:
        registry = build_registry(http)
        if args.fake:
            from ch06.scripted import SCENARIOS

            question, client = SCENARIOS[args.fake]()
            print("[fake model: scripted replies; the tool results come from the Kestrel API]")
            run_round_trip(client, registry, system, question, MAX_TOKENS)
            if args.wire:  # the follow-up request's messages, as the adapter sends them
                from ch06.anthropic_adapter import to_sdk_message

                sent = [to_sdk_message(m) for m in client.calls[1].messages]
                print(json.dumps(sent, indent=2))
            return
        if not args.question:
            parser.error("give a question, or --fake single|parallel")
        from ch06.anthropic_adapter import AnthropicAdapter
        from ch06.settings import Settings

        settings = Settings.from_env()
        if settings.api_key is None:
            raise SystemExit("error: set ANTHROPIC_API_KEY in .env (or use --fake)")
        client = AnthropicAdapter(settings)
        run_round_trip(client, registry, system, args.question, settings.max_output_tokens)


if __name__ == "__main__":
    main()
