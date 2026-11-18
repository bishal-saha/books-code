"""One test per branch of the workflow, against a fake transport (no server), plus one
end-to-end run against the seeded API."""

from datetime import date

import httpx
import pytest
from ch01.order_status import (
    NoOrderOnTicket,
    NotShipped,
    TicketNotFound,
    UpstreamUnavailable,
    Verdict,
    get_order_status,
    main,
)
from pydantic import ValidationError

TICKET = {"ticket_id": "T-1", "order_id": "O-1"}
ORDER = {"order_id": "O-1", "channel": "store"}


def shipment(status: str) -> dict:
    return {"carrier": "Swiftway Parcel", "status": status, "promised_by": "2025-12-05T10:00:00"}


def fake_client(routes: dict[str, dict | None]) -> httpx.Client:
    """A client whose API answers from `routes`; None or a missing path is a 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(request.url.path)
        if body is None:
            return httpx.Response(404, json={"error": f"no {request.url.path}"})
        return httpx.Response(200, json=body)

    return httpx.Client(base_url="http://kestrel.test", transport=httpx.MockTransport(handler))


def routes_with(status: str) -> dict[str, dict | None]:
    return {"/tickets/T-1": TICKET, "/orders/O-1": ORDER, "/orders/O-1/shipment": shipment(status)}


@pytest.mark.parametrize(
    ("status", "today", "verdict"),
    [
        ("delivered", date(2025, 12, 16), Verdict.DELIVERED),
        ("lost", date(2025, 12, 1), Verdict.LOST),  # lost before the promised date
        ("in_transit", date(2025, 12, 16), Verdict.LATE),
        ("in_transit", date(2025, 12, 5), Verdict.ON_TIME),  # the promised day itself
    ],
)
def test_verdicts(status: str, today: date, verdict: Verdict) -> None:
    result = get_order_status(fake_client(routes_with(status)), "T-1", today)
    assert result.verdict is verdict
    assert result.promised_by == date(2025, 12, 5)


def test_unknown_ticket() -> None:
    with pytest.raises(TicketNotFound):
        get_order_status(fake_client({}), "T-404", date(2025, 12, 16))


def test_ticket_without_order() -> None:
    routes = {"/tickets/T-1": {"ticket_id": "T-1", "order_id": None}}
    with pytest.raises(NoOrderOnTicket):
        get_order_status(fake_client(routes), "T-1", date(2025, 12, 16))


def test_order_not_shipped() -> None:
    routes = {"/tickets/T-1": TICKET, "/orders/O-1": ORDER}
    with pytest.raises(NotShipped):
        get_order_status(fake_client(routes), "T-1", date(2025, 12, 16))


def test_server_error_is_upstream_unavailable() -> None:
    client = httpx.Client(
        base_url="http://kestrel.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    with pytest.raises(UpstreamUnavailable):
        get_order_status(client, "T-1", date(2025, 12, 16))


def test_api_mismatch_is_a_validation_error() -> None:
    routes = routes_with("in_transit")
    routes["/orders/O-1/shipment"] = {"carrier": "Swiftway Parcel", "status": "returned"}
    with pytest.raises(ValidationError):
        get_order_status(fake_client(routes), "T-1", date(2025, 12, 16))


def test_undeclared_fields_are_ignored() -> None:
    routes = routes_with("delivered")
    routes["/orders/O-1"] = {**ORDER, "total": 129.0, "currency": "USD"}
    result = get_order_status(fake_client(routes), "T-1", date(2025, 12, 16))
    assert result.verdict is Verdict.DELIVERED


def test_seeded_ticket_end_to_end(kestrel_url: str) -> None:
    with httpx.Client(base_url=kestrel_url, timeout=5.0) as client:
        result = get_order_status(client, "T-000407", date(2025, 12, 16))
    assert (result.order_id, result.verdict) == ("O-0006066", Verdict.LATE)


def test_cli_rejects_bad_date(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["order_status", "T-000407", "16/12/2025"]) == 2
    assert "usage:" in capsys.readouterr().err
