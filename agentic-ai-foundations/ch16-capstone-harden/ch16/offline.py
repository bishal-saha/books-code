"""New in Chapter 16: a pretend search service for tests, demos and the offline eval.

It serves the hand-written fixture (fixtures/search/carriers.json) through HttpSearchBackend
and httpx.MockTransport, so the real request, status handling and retry code all run with no
network. `statuses` are answered in order before the fixture's results: [503] fails the first
request once, and `then=401` makes every later request fail as well.
"""

from collections.abc import Sequence
from pathlib import Path

import httpx
from pydantic import SecretStr

from ch16.tools import FixtureSearchBackend, HttpSearchBackend

FOLDER = Path(__file__).resolve().parent.parent
SEARCH_FIXTURE = FOLDER / "fixtures" / "search" / "carriers.json"


class OfflineSearchService:
    def __init__(
        self, statuses: Sequence[int] = (), then: int = 200, fixture: Path = SEARCH_FIXTURE
    ) -> None:
        self._results = FixtureSearchBackend(fixture)
        self._statuses = list(statuses)
        self._then = then
        self.requests: list[str] = []  # the query of every request received

    def handle(self, request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        self.requests.append(query)
        status = self._statuses.pop(0) if self._statuses else self._then
        if status != 200:
            return httpx.Response(status, json={"error": "offline service: scripted failure"})
        hits = self._results.search(query, int(request.url.params["count"]), timeout_s=0)
        return httpx.Response(200, json={"results": [h.model_dump() for h in hits]})

    def backend(self) -> HttpSearchBackend:
        client = httpx.Client(transport=httpx.MockTransport(self.handle))
        return HttpSearchBackend("https://search.invalid/v1", SecretStr("offline"), client)
