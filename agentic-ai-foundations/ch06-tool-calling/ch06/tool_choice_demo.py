"""Tool choice, four ways: what each mode sends, and (with a key) what the model does.

uv run python -m ch06.tool_choice_demo --show      # the tool_choice each mode sends; no key
uv run --env-file .env python -m ch06.tool_choice_demo
"""

import argparse
import json

import httpx

from ch06.anthropic_adapter import to_sdk_tool_choice
from ch06.model_client import Message, ModelError, ToolChoice
from ch06.prompts import load_prompt
from ch06.settings import Settings
from ch06.tools import build_registry

QUESTION = "Is order O-0000141 for Lakeside Lodge 1755 still open?"
MODES = {
    "allow (auto)": ToolChoice(),
    "require (required)": ToolChoice(mode="required"),
    "require get_order (tool)": ToolChoice(mode="tool", tool_name="get_order"),
    "forbid (none)": ToolChoice(mode="none"),
    "allow, one call at most": ToolChoice(allow_parallel=False),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one question once per tool choice mode.")
    parser.add_argument("--show", action="store_true", help="print the requests' tool_choice only")
    args = parser.parse_args()
    if args.show:
        for label, choice in MODES.items():
            print(f"{label:26} -> {json.dumps(to_sdk_tool_choice(choice))}")
        return

    from ch06.anthropic_adapter import AnthropicAdapter

    settings = Settings.from_env()
    client = AnthropicAdapter(settings)
    system = load_prompt("order_lookup", 1).body
    with httpx.Client(base_url=settings.kestrel_url, timeout=5.0) as http:
        tools = build_registry(http).definitions()
    messages = [Message(role="user", content=QUESTION)]
    for label, choice in MODES.items():  # one model call per mode, no tools are run
        try:
            r = client.complete(system, messages, settings.max_output_tokens, tools, choice)
        except ModelError as err:  # e.g. a model that does not support forced tool use
            print(f"{label:26} -> error: {err}")
            continue
        names = ", ".join(c.name for c in r.tool_calls) or "no tool call"
        print(f"{label:26} -> {r.stop_reason}: {names}")


if __name__ == "__main__":
    main()
