"""Validate model output against a pydantic model, and retry with the errors, a bounded number
of times. Nothing here knows about expense claims: any output model works."""

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails

from ch05.model_client import Message, ModelClient, StopReason

_FENCED = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Remove markdown fences only when they wrap the whole response."""
    match = _FENCED.match(text)
    return match.group(1) if match else text


def validate_output[T: BaseModel](
    text: str, output_model: type[T], context: dict[str, Any] | None = None
) -> T | list[ErrorDetails]:
    try:
        return output_model.model_validate_json(strip_fences(text), context=context)
    except ValidationError as exc:
        return exc.errors(include_url=False, include_input=False)


@dataclass(frozen=True)
class Attempt:
    number: int
    stop_reason: StopReason
    raw_text: str
    errors: list[ErrorDetails]
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Extraction[T: BaseModel]:
    value: T
    attempts: list[Attempt]


FailureReason = Literal["truncated", "stopped", "invalid"]


class ExtractionFailed(Exception):
    def __init__(self, reason: FailureReason, attempts: list[Attempt]) -> None:
        super().__init__(f"{reason} after {len(attempts)} attempt(s)")
        self.reason = reason
        self.attempts = attempts  # every attempt, with its text, errors and tokens


def format_feedback(errors: list[ErrorDetails]) -> str:
    lines = [f"- {'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}" for e in errors]
    return (
        "Your previous output failed validation:\n"
        + "\n".join(lines)
        + "\nReturn the corrected JSON object only, with no other text."
    )


def extract[T: BaseModel](
    client: ModelClient,
    system: str,
    user_message: str,
    output_model: type[T],
    *,
    max_attempts: int,
    max_tokens: int,
    context: dict[str, Any] | None = None,
) -> Extraction[T]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    messages = [Message(role="user", content=user_message)]
    attempts: list[Attempt] = []

    for number in range(1, max_attempts + 1):
        response = client.complete(system, messages, max_tokens)
        finished = response.stop_reason == "finished"
        result = validate_output(response.text, output_model, context) if finished else []
        errors = [] if isinstance(result, BaseModel) else result
        tokens = (response.usage.input_tokens, response.usage.output_tokens)
        attempts.append(Attempt(number, response.stop_reason, response.text, errors, *tokens))

        if response.stop_reason == "truncated":
            raise ExtractionFailed("truncated", attempts)  # a settings problem: don't retry
        if not finished:
            raise ExtractionFailed("stopped", attempts)  # refusal or anything unexpected
        if isinstance(result, BaseModel):
            return Extraction(result, attempts)

        messages = [  # a new list, so a request that was already sent never changes
            *messages,
            Message(role="assistant", content=response.text),
            Message(role="user", content=format_feedback(errors)),
        ]

    raise ExtractionFailed("invalid", attempts)
