"""Grace's policy questions, two ways: the whole handbook in the prompt, or two doc tools.

uv run python -m ch09.handbook_compare --fake        # scripted replies, no key
uv run python -m ch09.handbook_compare --fake --crossover   # grow the folder, find the crossover
uv run --env-file .env python -m ch09.handbook_compare
"""

import argparse
import shutil
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

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


def stale_sent(q: PolicyQuestion, texts: list[str]) -> bool | None:
    """Did a phrase only the retired page contains reach the model? None: nothing to check."""
    if not q.stale_facts:
        return None
    return any(f in t for f in q.stale_facts for t in texts)


def request_texts(messages: list[Message]) -> list[str]:
    """Everything a run sent besides the system prompt: messages and tool results."""
    return [m.content for m in messages] + [r.content for m in messages for r in m.tool_results]


class Row(BaseModel):
    question: str
    variant: str
    steps: int
    input_tokens: int  # summed over every step's request
    answer: str
    read_paths: set[str] | None
    stale_sent: bool | None  # the retired page's own wording was in a request


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
                        answer=answer_a, read_paths=None,
                        stale_sent=stale_sent(q, [system])))  # fmt: skip
        result = ask_with_tools(client_b, root, q.question, budget, limits, context)
        tokens_b = sum(s.context.total_input for s in result.steps if s.context)
        rows.append(Row(question=q.id, variant="B", steps=len(result.steps),
                        input_tokens=tokens_b, answer=result.final_text,
                        read_paths=paths_read(result),
                        stale_sent=stale_sent(q, request_texts(result.messages))))  # fmt: skip
    return rows


def print_rows(rows: list[Row], graded: bool) -> None:
    by_id = {q.id: q for q in QUESTIONS}
    header = f"{'question':<22}{'variant':<9}{'steps':<7}{'input tokens':<14}{'stale sent':<12}"
    print((header + ("correct  stale" if graded else "")).rstrip())
    for r in rows:
        sent = "-" if r.stale_sent is None else ("yes" if r.stale_sent else "no")
        line = f"{r.question:<22}{r.variant:<9}{r.steps:<7}{r.input_tokens:<14}{sent:<12}"
        if graded:
            q = by_id[r.question]
            ok, stale = is_correct(q, r.answer, r.read_paths), quotes_stale(q, r.answer)
            line += f"{'yes' if ok else 'no':<9}{'yes' if stale else 'no'}"
        print(line.rstrip())


FILLER = (
    "Kestrel staff use this page for day-to-day notes. It is synthetic filler for the growth "
    "experiment: it answers none of Grace's questions, it only makes the folder bigger. "
)


def grow_folder(src: Path, dst: Path, extra: int) -> Path:
    """A copy of the docs plus `extra` synthetic filler pages of about 1,700 characters."""
    shutil.copytree(src, dst)
    for n in range(1, extra + 1):
        text = f"# Wiki page {n:02d} (synthetic filler)\n\n" + FILLER * 10
        (dst / f"wiki-{n:02d}.md").write_text(text, encoding="utf-8")
    return dst


def crossover(src: Path, sizes: tuple[int, ...] = (0, 2, 4, 8, 32)) -> None:
    """The trade question on growing folders, with the scripted fake model."""
    from ch09.scripted import FAKE_BUDGET, FAKE_CONTEXT, FAKE_LIMITS, handbook_clients

    question = QUESTIONS[:1]
    print(f"{'filler pages':<14}{'docs chars':<12}{'A tokens':<10}B tokens")
    for extra in sizes:
        with TemporaryDirectory() as tmp:
            root = grow_folder(src, Path(tmp) / "docs", extra)
            chars = sum(len((root / p).read_text(encoding="utf-8")) for p in doc_paths(root))
            a, b = compare(*handbook_clients(question), root, question,
                           FAKE_BUDGET, FAKE_LIMITS, FAKE_CONTEXT)  # fmt: skip
        print(f"{extra:<14}{chars:<12}{a.input_tokens:<10}{b.input_tokens}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two context designs.")
    parser.add_argument("--fake", action="store_true", help="scripted fake model, no key")
    parser.add_argument("--docs", type=Path, default=DOCS_ROOT)
    parser.add_argument("--crossover", action="store_true", help="with --fake: grow the folder")
    args = parser.parse_args()
    if not doc_paths(args.docs):
        raise SystemExit(f"error: no docs in {args.docs}; run `uv run kestrel up` here first")
    if args.crossover:
        if not args.fake:
            parser.error("--crossover needs --fake")
        print("[fake model: scripted replies; token counts are local estimates]")
        crossover(args.docs)
        return

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
