"""Grace's policy questions, two ways: the whole handbook in the prompt, or two doc tools.

uv run python -m ch09.handbook_compare --fake        # scripted replies, no key
uv run --env-file .env python -m ch09.handbook_compare
"""

import argparse
from html import escape
from pathlib import Path

from pydantic import BaseModel

from ch09.agent import RunResult, run_agent
from ch09.budget import CallLimits, RunBudget
from ch09.context_budget import ContextBudget, context_budget_from
from ch09.doc_tools import DOCS_ROOT, build_doc_registry, doc_paths
from ch09.grade import PolicyQuestion, is_correct, quotes_stale
from ch09.inspector import ContextInspector
from ch09.model_client import Message, ModelClient, ModelResponse
from ch09.prompts import load_prompt
from ch09.questions import QUESTIONS
from ch09.settings import Settings


def render_handbook(root: Path) -> str:
    """Every doc, each wrapped in a tag that carries its path, tag characters escaped."""
    return "\n".join(
        f'<doc path="{escape(path)}">\n'
        f"{escape((root / path).read_text(encoding='utf-8'), quote=False)}\n</doc>"
        for path in sorted(doc_paths(root))
    )


def handbook_request(root: Path, question: str) -> tuple[str, list[Message]]:
    system = load_prompt("handbook", 1).body.replace("{data}", render_handbook(root))
    return system, [Message(role="user", content=question)]


def ask_whole_handbook(
    client: ModelClient, root: Path, question: str, limits: CallLimits
) -> ModelResponse:
    system, messages = handbook_request(root, question)
    return client.complete(system, messages, limits.max_output_tokens,
                           timeout=limits.timeout_seconds)  # fmt: skip


def ask_with_tools(
    client: ModelClient,
    root: Path,
    question: str,
    budget: RunBudget,
    limits: CallLimits,
    context: ContextBudget,
) -> RunResult:
    registry = build_doc_registry(root, context.tool_result_max_chars)
    return run_agent(client, load_prompt("docs_agent", 1).body, question, registry,
                     budget, limits, inspector=ContextInspector(client, context))  # fmt: skip


def paths_read(result: RunResult) -> set[str]:
    return {
        str(c.arguments.get("path"))
        for step in result.steps
        for c in step.tool_calls
        if c.name == "read_doc" and not c.is_error
    }


class Row(BaseModel):
    question: str
    variant: str
    steps: int
    input_tokens: int  # summed over every step's request
    answer: str
    read_paths: set[str] | None


def compare(
    client_a: ModelClient,
    client_b: ModelClient,
    root: Path,
    questions: list[PolicyQuestion],
    budget: RunBudget,
    limits: CallLimits,
    context: ContextBudget,
) -> list[Row]:
    rows = []
    for q in questions:
        system, messages = handbook_request(root, q.question)
        tokens_a = client_a.count_tokens(system, messages)
        answer_a = ask_whole_handbook(client_a, root, q.question, limits).text
        rows.append(Row(question=q.id, variant="A", steps=1, input_tokens=tokens_a,
                        answer=answer_a, read_paths=None))  # fmt: skip
        result = ask_with_tools(client_b, root, q.question, budget, limits, context)
        tokens_b = sum(s.context.total_input for s in result.steps if s.context)
        rows.append(Row(question=q.id, variant="B", steps=len(result.steps),
                        input_tokens=tokens_b, answer=result.final_text,
                        read_paths=paths_read(result)))  # fmt: skip
    return rows


def print_rows(rows: list[Row], graded: bool) -> None:
    by_id = {q.id: q for q in QUESTIONS}
    header = f"{'question':<22}{'variant':<9}{'steps':<7}{'input tokens':<14}"
    print((header + ("correct  stale" if graded else "")).rstrip())
    for r in rows:
        line = f"{r.question:<22}{r.variant:<9}{r.steps:<7}{r.input_tokens:<14}"
        if graded:
            q = by_id[r.question]
            ok, stale = is_correct(q, r.answer, r.read_paths), quotes_stale(q, r.answer)
            line += f"{'yes' if ok else 'no':<9}{'yes' if stale else 'no'}"
        print(line.rstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two context designs.")
    parser.add_argument("--fake", action="store_true", help="scripted fake model, no key")
    parser.add_argument("--docs", type=Path, default=DOCS_ROOT)
    args = parser.parse_args()
    if not doc_paths(args.docs):
        raise SystemExit(f"error: no docs in {args.docs}; run `uv run kestrel up` here first")

    sizes = [len((args.docs / p).read_text(encoding="utf-8")) for p in doc_paths(args.docs)]
    print(f"handbook: {len(sizes)} docs, {sum(sizes)} chars")
    if args.fake:
        from ch09.scripted import FAKE_BUDGET, FAKE_CONTEXT, FAKE_LIMITS, handbook_clients

        client_a, client_b = handbook_clients(QUESTIONS)
        budget, limits, context = FAKE_BUDGET, FAKE_LIMITS, FAKE_CONTEXT
        print("[fake model: scripted replies; token counts are local estimates of the real "
              "requests]")  # fmt: skip
    else:
        from ch09.anthropic_adapter import AnthropicAdapter

        settings = Settings.from_env()
        if settings.api_key is None:
            raise SystemExit("error: set ANTHROPIC_API_KEY in .env (or use --fake)")
        client_a = client_b = AnthropicAdapter(settings)
        budget = RunBudget(settings.run_max_steps, settings.run_max_tokens,
                           settings.run_max_seconds)  # fmt: skip
        limits = CallLimits(settings.max_output_tokens, settings.timeout_seconds)
        context = context_budget_from(settings)
    rows = compare(client_a, client_b, args.docs, QUESTIONS, budget, limits, context)
    print_rows(rows, graded=not args.fake)


if __name__ == "__main__":
    main()
