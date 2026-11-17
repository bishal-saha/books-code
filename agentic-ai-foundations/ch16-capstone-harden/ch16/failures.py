"""New in Chapter 16: every failure is transient or permanent, decided in one place.

Transient: the same request may work after a wait (a timeout, a dropped connection, a rate
limit, an overloaded service). Permanent: the same request fails the same way until something
changes, either the request (the model can send another one) or the setup (a person must fix a
key, a price or a setting). Only transient failures are worth retrying in code.
"""

from enum import StrEnum

import httpx

from ch16.model_client import ModelError


class FailureKind(StrEnum):
    TRANSIENT = "transient"  # the same request may succeed after a wait
    PERMANENT = "permanent"  # the same request fails until the request or the setup changes


class SearchHTTPError(Exception):
    """The search service answered with an error status. Raised by HttpSearchBackend."""

    def __init__(self, status: int, retry_after_s: float | None = None) -> None:
        super().__init__(f"the search service answered HTTP {status}")
        self.status = status
        self.retry_after_s = retry_after_s  # from a Retry-After header in seconds, if any


TRANSIENT_STATUS = {408, 429}  # request timeout, rate limit; and every 5xx
TRANSIENT_MODEL_ERRORS = {"timeout", "rate_limited", "provider_error"}  # from Chapter 3


def classify(exc: BaseException) -> FailureKind:
    if isinstance(exc, ModelError):  # the adapter already mapped the SDK's error to a kind
        transient = exc.kind in TRANSIENT_MODEL_ERRORS
        return FailureKind.TRANSIENT if transient else FailureKind.PERMANENT
    if isinstance(exc, SearchHTTPError):
        transient = exc.status in TRANSIENT_STATUS or exc.status >= 500
        return FailureKind.TRANSIENT if transient else FailureKind.PERMANENT
    if isinstance(exc, httpx.TransportError):  # timeouts, refused or dropped connections
        return FailureKind.TRANSIENT
    return FailureKind.PERMANENT  # a ToolError, or anything we don't understand: never retry
