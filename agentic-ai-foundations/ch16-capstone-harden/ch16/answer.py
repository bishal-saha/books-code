"""FinalAnswer: the research assistant's answer, in a shape code can check."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, model_validator

NEEDS_INFO = "NEEDS INFO"  # Chapter 4's don't-know marker
REFUSAL_MAX_CHARS = 300  # one or two sentences saying what is missing


class Citation(BaseModel):
    kind: Literal["url", "file"]
    location: str = Field(
        description="A URL search_web returned, or a file path read_file or count_rows returned"
    )
    supports: str = Field(max_length=200, description="What this citation supports, briefly")

    @model_validator(mode="after")
    def location_matches_kind(self) -> "Citation":
        if self.kind == "url" and not self.location.startswith(("https://", "http://")):
            raise ValueError("a url citation must start with http:// or https://")
        if self.kind == "file":
            path = PurePosixPath(self.location)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("a file citation is relative to the sandbox, without '..'")
        return self


class Claim(BaseModel):
    text: str = Field(description="One factual statement")
    citations: list[int] = Field(min_length=1, description="Indexes into FinalAnswer.citations")


class FinalAnswer(BaseModel):
    status: Literal["answered", "needs_info"]
    answer: str = Field(description="A short summary of the claims; adds no new facts")
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    missing: list[str] = Field(
        default_factory=list, description="What the sources did not cover; empty if nothing"
    )

    @model_validator(mode="after")
    def status_rules(self) -> "FinalAnswer":
        for claim in self.claims:
            if any(not 0 <= i < len(self.citations) for i in claim.citations):
                raise ValueError(f"claim {claim.text[:40]!r} cites an index that doesn't exist")
        if self.status == "answered":
            if not self.claims:
                raise ValueError("status 'answered' needs at least one claim")
            no_file = any(
                all(self.citations[i].kind == "url" for i in c.citations) for c in self.claims
            )
            if self.confidence == "high" and no_file:
                raise ValueError("high confidence needs a file citation on every claim")
        else:
            if not self.answer.startswith(NEEDS_INFO):
                raise ValueError(f"status 'needs_info' starts the answer with {NEEDS_INFO!r}")
            if len(self.answer) > REFUSAL_MAX_CHARS:
                raise ValueError(f"a needs_info answer stays under {REFUSAL_MAX_CHARS} characters")
            if not self.missing or self.claims:
                raise ValueError("status 'needs_info' lists what is missing and makes no claims")
        return self
