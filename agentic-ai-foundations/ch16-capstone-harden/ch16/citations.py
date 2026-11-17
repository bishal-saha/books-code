"""Citation checking: a citation counts only if a tool returned that URL or path in this run."""

from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from ch16.answer import FinalAnswer
from ch16.tools import CountRowsResult, SearchResult
from ch16.truncate import ProvenancedResult


class CitationError(BaseModel):
    index: int  # position in FinalAnswer.citations
    location: str
    reason: str


def normalise_url(url: str) -> str:
    """Lowercase the scheme and host and drop the fragment. The query stays: it can name a page."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def citable_locations(tool: str, output: object) -> set[str]:
    """What one successful tool output makes citable. Error results never reach this."""
    if tool == "search_web":
        return {normalise_url(SearchResult.model_validate(r).url) for r in output}
    if tool == "read_file" and isinstance(output, ProvenancedResult):
        return {output.origin}  # read_file sets origin to the file's sandbox name
    if tool == "count_rows" and isinstance(output, CountRowsResult):
        return {output.path}
    return set()  # calculate, and anything else, cites nothing


def check_citations(answer: FinalAnswer, returned: set[str]) -> list[CitationError]:
    """One error per citation whose location no tool returned in this run."""
    errors = []
    for i, citation in enumerate(answer.citations):
        location = citation.location
        if citation.kind == "url":
            key = normalise_url(location)
        else:
            key = PurePosixPath(location).as_posix()  # "./shipments.csv" -> "shipments.csv"
        if key not in returned:
            errors.append(
                CitationError(
                    index=i,
                    location=location,
                    reason="no tool returned this location in this run; cite only tool results",
                )
            )
    return errors
