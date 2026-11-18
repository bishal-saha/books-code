"""Count the tokens in one Kestrel docs page, check the fit, and price the call."""

import argparse
import math
import sys

import anthropic
from pydantic import BaseModel

from ch02.cost import estimate_cost
from ch02.settings import Settings

CHARS_PER_TOKEN = 4  # a labelled placeholder for rough sizing, never for budgets
LIMIT_STOPS = {"max_tokens", "model_context_window_exceeded"}  # stopped at a limit


class TokenCount(BaseModel):
    page: str
    characters: int
    heuristic_tokens: int
    counted_tokens: int | None  # None: no provider count, estimate only


class TokenCountError(RuntimeError):
    """The provider could not count the request."""


class WindowCheck(BaseModel):
    input_tokens: int
    max_tokens: int
    context_window: int
    input_fits: bool  # False: rejected on every model ("prompt is too long")
    fits: bool  # False: rejected on older models, may be cut short on newer ones
    output_headroom: int  # the largest max_tokens that still fits, never negative


def make_client(settings: Settings) -> anthropic.Anthropic:
    if settings.api_key is None:
        raise TokenCountError("set ANTHROPIC_API_KEY to call the provider")
    return anthropic.Anthropic(
        api_key=settings.api_key.get_secret_value(),
        timeout=settings.model_timeout_s,
        max_retries=2,
    )


def load_page(settings: Settings, page: str) -> str:
    path = settings.docs_dir / page
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; run `uv run kestrel up` first")
    return path.read_text(encoding="utf-8")


def count_text(
    settings: Settings, page: str, text: str, client: anthropic.Anthropic | None = None
) -> TokenCount:
    heuristic = math.ceil(len(text) / CHARS_PER_TOKEN)
    if client is None and settings.api_key is None:
        return TokenCount(
            page=page, characters=len(text), heuristic_tokens=heuristic, counted_tokens=None
        )
    client = client or make_client(settings)
    try:
        result = client.messages.count_tokens(
            model=settings.model,
            messages=[{"role": "user", "content": text}],
        )
    except anthropic.APIError as exc:
        raise TokenCountError(f"count_tokens failed for {page}: {exc}") from exc
    return TokenCount(
        page=page,
        characters=len(text),
        heuristic_tokens=heuristic,
        counted_tokens=result.input_tokens,
    )


def check_fits(input_tokens: int, max_tokens: int, context_window: int) -> WindowCheck:
    """Compare counted input plus planned output with the configured window."""
    if input_tokens < 0:
        raise ValueError("input_tokens must not be negative")
    if max_tokens <= 0 or context_window <= 0:
        raise ValueError("max_tokens and context_window must be positive")
    return WindowCheck(
        input_tokens=input_tokens,
        max_tokens=max_tokens,
        context_window=context_window,
        input_fits=input_tokens <= context_window,
        fits=input_tokens + max_tokens <= context_window,
        output_headroom=max(context_window - input_tokens, 0),
    )


def require_fit(counted: int | None, max_tokens: int, context_window: int) -> None:
    """Refuse a request before it is sent: no provider count, or it does not fit."""
    if counted is None:
        raise ValueError("no provider count to check the window with; set ANTHROPIC_API_KEY")
    if not check_fits(counted, max_tokens, context_window).fits:
        raise ValueError("prompt plus max_tokens does not fit the configured window")


def main() -> None:
    parser = argparse.ArgumentParser(description="Count and price one Kestrel docs page")
    parser.add_argument("page", help="file name under KESTREL_DOCS_DIR, e.g. returns-policy.md")
    parser.add_argument("--max-tokens", type=int, default=1_024, help="planned output cap")
    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        count = count_text(settings, args.page, load_page(settings, args.page))
    except (FileNotFoundError, TokenCountError) as exc:
        sys.exit(f"error: {exc}")
    counted = count.counted_tokens is not None
    tokens = count.counted_tokens if counted else count.heuristic_tokens
    label = "" if counted else "  (ESTIMATE: no API key)"
    check = check_fits(tokens, args.max_tokens, settings.context_window_tokens)
    print(f"page:                {count.page}")
    if counted:  # without a key no model is involved, so none is named
        print(f"model:               {settings.model}")
    print(f"characters:          {count.characters}")
    print(f"heuristic tokens:    {count.heuristic_tokens}")
    print(f"counted tokens:      {count.counted_tokens if counted else '-'}{label}")
    print(f"fits the window:     {check.fits} (max_tokens {args.max_tokens}){label}")
    print(f"input cost (USD):    {estimate_cost(tokens, 0, settings).total}{label}")
    print(f"worst case (USD):    {estimate_cost(tokens, args.max_tokens, settings).total}{label}")


if __name__ == "__main__":
    main()
