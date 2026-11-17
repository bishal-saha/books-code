"""Simple grading for Grace's policy questions: good enough to compare two designs."""

from pydantic import BaseModel


class PolicyQuestion(BaseModel):
    id: str
    question: str
    expected_path: str
    expected_facts: list[str]
    stale_facts: list[str] = []  # phrases only the retired page contains


def quotes_stale(q: PolicyQuestion, answer: str) -> bool:
    """Relying on the retired page, not merely naming it as superseded."""
    text = answer.lower()
    return any(f.lower() in text for f in q.stale_facts)


def is_correct(q: PolicyQuestion, answer: str, read_paths: set[str] | None = None) -> bool:
    """read_paths: the docs the run actually read (variant B). A path the model only saw in
    list_docs does not count. None means every doc was in the context (variant A)."""
    text = answer.lower()
    return (
        q.expected_path in answer
        and (read_paths is None or q.expected_path in read_paths)
        and all(f.lower() in text for f in q.expected_facts)
        and not quotes_stale(q, answer)
    )
