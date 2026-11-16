"""Print the user message the builder sends for one ticket. No model call, no key.

uv run python -m ch04.show_request T-000007
uv run python -m ch04.show_request ch04/fixtures/embedded_instruction.json
"""

import sys

import httpx

from ch04.compare import fetch_policies, load_ticket
from ch04.prompt_builder import render_ticket
from ch04.settings import Settings


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m ch04.show_request TICKET_ID_OR_FIXTURE", file=sys.stderr)
        return 2
    settings = Settings.from_env()
    with httpx.Client(base_url=settings.kestrel_url, timeout=5.0) as http:
        loaded = load_ticket(http, argv[0], fetch_policies(http))
    if loaded is None:
        print(f"error: no ticket {argv[0]}", file=sys.stderr)
        return 1
    print(render_ticket(*loaded))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
