"""Stream a draft reply to one Kestrel ticket: uv run --env-file .env python -m ch03.draft_reply"""

import argparse
import sys
from contextlib import closing

from pydantic import ValidationError

from ch03.model_client import (
    ConfigError,
    Message,
    ModelClient,
    ModelError,
    ModelResponse,
    build_client,
    call_cost_usd,
)
from ch03.settings import ENV_VARS, Settings
from ch03.ticket_prompt import SYSTEM_PROMPT, build_user_text, fetch_ticket

FIELD_TO_VAR = {field: var for var, field in ENV_VARS.items()}


def stream_draft(client: ModelClient, settings: Settings, messages: list[Message]) -> ModelResponse:
    final: ModelResponse | None = None
    printed = False
    with closing(client.stream(SYSTEM_PROMPT, messages, settings.max_output_tokens)) as items:
        try:
            for item in items:
                if isinstance(item, ModelResponse):
                    final = item
                else:
                    print(item, end="", flush=True)
                    printed = True
        except ModelError:
            if printed:
                print("\n[incomplete] The stream failed partway. The text above is not a draft.")
            raise
    print()
    if final is None:
        raise ModelError("provider_error", "the stream ended without a final response")
    return final


def print_footer(response: ModelResponse, settings: Settings) -> None:
    if response.stop_reason == "truncated":
        print("[truncated] This draft hit the output token limit. Do not send it as is.")
    elif response.stop_reason != "finished":
        print("[stopped] The model stopped for a reason this client does not handle yet.")
    cost = call_cost_usd(response.usage, settings)
    print(
        f"stop: {response.stop_reason} | in: {response.usage.input_tokens} "
        f"| out: {response.usage.output_tokens} | cost: ${cost:.6f}"
    )


def friendly_message(err: ModelError, settings: Settings) -> str:
    messages = {
        "timeout": f"The request timed out (MODEL_TIMEOUT_S={settings.timeout_seconds}, "
        f"MAX_RETRIES={settings.max_retries}).",
        "rate_limited": "The provider is rate limiting this API key. Try again shortly.",
        "auth": "The API key was rejected. Check ANTHROPIC_API_KEY.",
        "bad_request": "The provider rejected the request. Check MODEL and MAX_OUTPUT_TOKENS.",
        "provider_error": "The provider could not be reached or returned an error.",
    }
    return messages[err.kind]


def run(client: ModelClient, settings: Settings, ticket: dict, *, stream: bool = True) -> int:
    messages = [Message(role="user", content=build_user_text(ticket))]
    try:
        if stream:
            response = stream_draft(client, settings, messages)
        else:
            response = client.complete(SYSTEM_PROMPT, messages, settings.max_output_tokens)
            print(response.text)
    except ModelError as err:
        print(f"error: {friendly_message(err, settings)}", file=sys.stderr)
        if err.request_id:
            print(f"request id: {err.request_id}", file=sys.stderr)
        return 1
    print_footer(response, settings)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a reply to one Kestrel ticket.")
    parser.add_argument("ticket_id", help="for example T-000407")
    parser.add_argument("--no-stream", action="store_true", help="wait for the whole reply")
    args = parser.parse_args()

    try:
        settings = Settings.from_env()  # fails fast on missing configuration
    except ValidationError as exc:
        names = ", ".join(FIELD_TO_VAR[str(e["loc"][0])] for e in exc.errors())
        raise SystemExit(f"error: missing or invalid settings: {names}") from None
    try:
        client = build_client(settings)  # no network yet: a missing key is reported first
    except ConfigError as exc:
        raise SystemExit(f"error: {exc}") from None
    ticket = fetch_ticket(settings.kestrel_url, args.ticket_id)  # before any model call
    try:
        code = run(client, settings, ticket, stream=not args.no_stream)
    except KeyboardInterrupt:
        print("\n[cancelled] The draft was abandoned.", file=sys.stderr)
        code = 130
    raise SystemExit(code)


if __name__ == "__main__":
    main()
