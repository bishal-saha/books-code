"""Send one question about the returns page N times and compare what comes back."""

import argparse
import os
import sys
from collections import Counter

import anthropic
from pydantic import BaseModel

from ch02.cost import CostEstimate, estimate_cost
from ch02.settings import Settings
from ch02.tokens import LIMIT_STOPS, count_text, load_page, make_client, require_fit

MAX_RUNS = 20  # ceiling on N, whatever the caller asks for
PAGE = "returns-policy.md"
QUESTION = "In one sentence: how many days does a consumer have to return an unused item?"


class SamplingReport(BaseModel):
    runs: int
    answers: list[str]
    distinct: int
    truncated: int  # stopped at a token limit; not counted as variants
    cost: CostEstimate


def prompt_for(page_text: str) -> str:
    return f"{page_text}\n\n{QUESTION}"


def run_demo(
    client: anthropic.Anthropic, settings: Settings, page_text: str, runs: int, max_tokens: int
) -> SamplingReport:
    prompt = prompt_for(page_text)
    counted = count_text(settings, PAGE, prompt, client).counted_tokens
    require_fit(counted, max_tokens, settings.context_window_tokens)
    answers: list[str] = []
    truncated = input_tokens = output_tokens = 0
    for _ in range(min(runs, MAX_RUNS)):
        response = client.messages.create(  # same request every time, nothing else varies
            model=settings.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            timeout=settings.model_timeout_s,
        )
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens  # truncated runs are still billed
        if response.stop_reason in LIMIT_STOPS:
            truncated += 1
            continue
        answers.append("".join(b.text for b in response.content if b.type == "text").strip())
    return SamplingReport(
        runs=min(runs, MAX_RUNS),
        answers=answers,
        distinct=len(set(answers)),
        truncated=truncated,
        cost=estimate_cost(input_tokens, output_tokens, settings),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one prompt several times")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    settings = Settings.from_env()
    max_tokens = int(os.environ.get("SAMPLING_MAX_TOKENS", "1024"))
    try:
        report = run_demo(
            make_client(settings), settings, load_page(settings, PAGE), args.runs, max_tokens
        )
    except (anthropic.APIError, FileNotFoundError, ValueError, RuntimeError) as exc:
        sys.exit(f"error: {exc}")
    print(f"runs: {report.runs}  distinct: {report.distinct}  truncated: {report.truncated}")
    for answer, times in Counter(report.answers).most_common():
        print(f"{times} x {answer}")
    print(f"tokens in/out: {report.cost.input_tokens}/{report.cost.output_tokens}")
    print(f"cost (USD): {report.cost.total}")


if __name__ == "__main__":
    main()
