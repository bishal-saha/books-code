"""Final-answer checking: Chapter 5's validation, Chapter 14's citation check, one retry message.

check_final turns the model's last message into a FinalCheck: the parsed FinalAnswer (when the
JSON validates) and a list of errors (empty when the answer is accepted). The loop sends
retry_message back once; what happens after a second failure is decided in run_agent.
"""

import re
from dataclasses import dataclass, field
from html import escape

from pydantic import ValidationError

from ch16.answer import FinalAnswer
from ch16.citations import check_citations

_FENCED = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Chapter 5: remove markdown fences only when they wrap the whole response."""
    match = _FENCED.match(text)
    return match.group(1) if match else text


@dataclass(frozen=True)
class FinalCheck:
    answer: FinalAnswer | None  # None when the text isn't a valid FinalAnswer
    errors: list[str] = field(default_factory=list)  # empty: accepted

    @property
    def accepted(self) -> bool:
        return self.answer is not None and not self.errors


def check_final(text: str, citable: set[str]) -> FinalCheck:
    try:
        answer = FinalAnswer.model_validate_json(strip_fences(text))
    except ValidationError as exc:
        return FinalCheck(
            None,
            [
                f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
                for e in exc.errors(include_url=False, include_input=False)
            ],
        )
    errors = [
        f"citations.{e.index}: {e.location!r}: {e.reason}" for e in check_citations(answer, citable)
    ]
    return FinalCheck(answer, errors)


def retry_message(check: FinalCheck, citable: set[str]) -> str:
    """The one retry: what failed, and every location the run can cite (as data)."""
    listing = "\n".join(sorted(citable)) or "(nothing: no tool has returned a location yet)"
    return (
        "Your final answer was rejected:\n"
        + "\n".join(f"- {e}" for e in check.errors)
        + "\nCitable locations in this run:\n"
        + f"<data>{escape(listing, quote=False)}</data>\n"
        + "Reply with the corrected JSON object only. If the sources don't support an answer, "
        + 'use status "needs_info".'
    )
