"""Ask one multi-step question about the returns page at two effort levels."""

import argparse
import os
import sys
import time
from typing import Literal

import anthropic
from pydantic import BaseModel

from ch02.cost import CostEstimate, estimate_cost
from ch02.settings import Settings
from ch02.tokens import LIMIT_STOPS, count_text, load_page, make_client, require_fit

Effort = Literal["low", "medium", "high"]
PAGE = "returns-policy.md"
QUESTION = (
    "A trade customer received a damaged tent 10 days ago and an unused stove 20 days ago. "
    "The refund for the tent alone would be USD 640. Using only the policy above: which "
    "items can go back, who pays return shipping, and who must approve the refund?"
)


class ReasoningRun(BaseModel):
    effort: Effort
    answer: str
    thinking_blocks: int
    output_tokens: int  # billed output, reasoning included
    thinking_tokens: int | None  # the reasoning part, when the response reports it
    latency_s: float
    stop_reason: str | None
    truncated: bool  # stopped at a limit: a failure, not a short answer
    cost: CostEstimate


def ask(
    client: anthropic.Anthropic,
    settings: Settings,
    page_text: str,
    effort: Effort,
    max_tokens: int,
) -> ReasoningRun:
    prompt = f"{page_text}\n\n{QUESTION}"
    counted = count_text(settings, PAGE, prompt, client).counted_tokens
    require_fit(counted, max_tokens, settings.context_window_tokens)
    started = time.monotonic()
    response = client.messages.create(
        model=settings.model,
        max_tokens=max_tokens,  # must hold the reasoning tokens and the answer
        thinking={"type": "adaptive"},  # the model decides whether and how much to reason
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
        timeout=settings.model_timeout_s,
    )
    details = response.usage.output_tokens_details
    return ReasoningRun(
        effort=effort,
        answer="".join(b.text for b in response.content if b.type == "text"),
        thinking_blocks=sum(1 for b in response.content if b.type == "thinking"),
        output_tokens=response.usage.output_tokens,
        thinking_tokens=details.thinking_tokens if details else None,
        latency_s=time.monotonic() - started,
        stop_reason=response.stop_reason,
        truncated=response.stop_reason in LIMIT_STOPS,
        cost=estimate_cost(response.usage.input_tokens, response.usage.output_tokens, settings),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two effort levels on one question")
    parser.add_argument(
        "--efforts", nargs="+", default=["low", "high"], choices=["low", "medium", "high"]
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    max_tokens = int(os.environ.get("REASONING_MAX_TOKENS", "16000"))
    try:
        client = make_client(settings)
        page_text = load_page(settings, PAGE)
        for effort in args.efforts:
            run = ask(client, settings, page_text, effort, max_tokens)
            print(run.model_dump_json(indent=2, exclude={"answer"}))
            print(run.answer, "\n")
    except (anthropic.APIError, FileNotFoundError, ValueError, RuntimeError) as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
