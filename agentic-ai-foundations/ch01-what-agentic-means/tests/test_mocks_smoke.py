import httpx
import pytest

SEEDED_PATHS = [
    "/tickets/T-000407",
    "/orders/O-0006066",
    "/orders/O-0006066/shipment",
    "/stock/SKU-00061",
    "/policies/shipping-policy",
    "/policies/returns-policy",
]


def test_health(kestrel_url: str) -> None:
    response = httpx.get(f"{kestrel_url}/health", timeout=5.0)
    response.raise_for_status()
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", SEEDED_PATHS)
def test_seeded_record(kestrel_url: str, path: str) -> None:
    response = httpx.get(f"{kestrel_url}{path}", timeout=5.0)
    assert response.status_code == 200, f"{path} returned HTTP {response.status_code}"
    assert response.json()
