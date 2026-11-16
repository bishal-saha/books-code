import json
import urllib.error
import urllib.request

import pytest
from kestrel.services import serve_in_thread


@pytest.fixture(scope="module")
def base_url():
    server, url = serve_in_thread(scale=0.02)
    yield url
    server.shutdown()


def get(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


def test_health(base_url) -> None:
    assert get(f"{base_url}/health") == (200, {"status": "ok"})


def test_order_and_shipment(base_url) -> None:
    shipments = get(f"{base_url}/shipments?limit=1")[1]
    order_id = shipments[0]["order_id"]
    status, order = get(f"{base_url}/orders/{order_id}")
    assert status == 200 and order["channel"] in ("store", "trade")
    status, shipment = get(f"{base_url}/orders/{order_id}/shipment")
    assert shipment["order_id"] == order_id and isinstance(shipment["late"], bool)


def test_filters_and_stock_and_policies(base_url) -> None:
    late = get(f"{base_url}/shipments?late=true&limit=5")[1]
    assert late and all(s["late"] for s in late)
    stock = get(f"{base_url}/stock/SKU-00001")[1]
    assert stock["warehouses"] and stock["sku"] == "SKU-00001"
    names = get(f"{base_url}/policies")[1]
    assert "shipping-policy" in names
    assert "Shipping policy" in get(f"{base_url}/policies/shipping-policy")[1]["body"]


def test_unknown_id_is_404(base_url) -> None:
    with pytest.raises(urllib.error.HTTPError) as err:
        get(f"{base_url}/orders/O-9999999")
    assert err.value.code == 404
