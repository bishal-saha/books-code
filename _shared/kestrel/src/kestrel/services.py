"""The Kestrel Outfitters mock API: read-only JSON over HTTP, standard library only.

`kestrel up` starts it on http://127.0.0.1:8700 (see UNIVERSE.md for the contract).
Book examples call it with httpx exactly as they would call a real internal API.
Tests start it in a thread with `serve_in_thread()`.

    GET /health
    GET /orders/{order_id}
    GET /orders/{order_id}/shipment
    GET /shipments?carrier=&late=&limit=
    GET /stock/{sku}
    GET /tickets/{ticket_id}
    GET /tickets?status=&limit=
    GET /policies
    GET /policies/{name}
"""

from __future__ import annotations

import json
import threading
import zlib
from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from kestrel.data import Dataset, generate
from kestrel.data.model import Order, Shipment

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8700
WAREHOUSES = ["Main (Riverside)", "North (Eastgate)"]


def _json(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


class KestrelData:
    """Indexes over one generated dataset, shaped the way the API returns them."""

    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        self.customers = {c.id: c for c in dataset.customers}
        self.orders = {o.id: o for o in dataset.orders}
        self.shipments_by_order = {s.order_id: s for s in dataset.shipments}
        self.products = {p.sku: p for p in dataset.products}
        self.tickets = {t.id: t for t in dataset.tickets}
        self.policies = {
            doc.name.removesuffix(".md"): doc.read_text()
            for doc in files("kestrel.docs").iterdir()
            if doc.name.endswith(".md") and doc.name != "README.md"
        }

    def order(self, o: Order) -> dict[str, object]:
        customer = self.customers[o.customer_id]
        shipment = self.shipments_by_order.get(o.id)
        promised = shipment.promised_by if shipment else o.placed_at + timedelta(days=3)
        return {
            "order_id": o.id,
            "customer_id": o.customer_id,
            "channel": "trade" if customer.type.value == "trade" else "store",
            "placed_at": o.placed_at,
            "status": o.status,
            "currency": o.currency,
            "total": round(o.total_cents / 100, 2),
            "promised_date": promised.date().isoformat(),
        }

    @staticmethod
    def shipment(s: Shipment) -> dict[str, object]:
        return {
            "shipment_id": s.id,
            "order_id": s.order_id,
            "carrier": s.carrier,
            "warehouse": s.warehouse,
            "shipped_at": s.shipped_at,
            "promised_by": s.promised_by,
            "delivered_at": s.delivered_at,
            "status": s.status,
            "late": s.late,
        }

    def stock(self, sku: str) -> dict[str, object]:
        product = self.products[sku]
        seed = zlib.crc32(sku.encode())
        levels = [
            {"warehouse": w, "on_hand": (seed >> (i * 8)) % 120 if product.active else 0}
            for i, w in enumerate(WAREHOUSES)
        ]
        return {"sku": sku, "name": product.name, "warehouses": levels}

    @staticmethod
    def ticket(t) -> dict[str, object]:
        return {
            "ticket_id": t.id,
            "customer_id": t.customer_id,
            "order_id": t.order_id,
            "channel": t.channel,
            "priority": t.priority,
            "status": t.status,
            "subject": t.subject,
            "messages": [asdict(m) for m in t.messages],
        }


class NotFound(Exception):
    pass


def route(data: KestrelData, path: str, query: dict[str, list[str]]) -> object:
    parts = [p for p in path.split("/") if p]
    q = {k: v[0] for k, v in query.items()}
    limit = min(int(q.get("limit", "50")), 500)
    match parts:
        case ["health"]:
            return {"status": "ok"}
        case ["orders", order_id]:
            if order_id not in data.orders:
                raise NotFound(f"no order {order_id}")
            return data.order(data.orders[order_id])
        case ["orders", order_id, "shipment"]:
            if order_id not in data.orders:
                raise NotFound(f"no order {order_id}")
            if order_id not in data.shipments_by_order:
                raise NotFound(f"order {order_id} has not shipped")
            return data.shipment(data.shipments_by_order[order_id])
        case ["shipments"]:
            rows = data.dataset.shipments
            if "carrier" in q:
                rows = [s for s in rows if s.carrier.lower() == q["carrier"].lower()]
            if "late" in q:
                want = q["late"].lower() in ("1", "true", "yes")
                rows = [s for s in rows if s.late == want]
            return [data.shipment(s) for s in rows[:limit]]
        case ["stock", sku]:
            if sku not in data.products:
                raise NotFound(f"no product {sku}")
            return data.stock(sku)
        case ["tickets", ticket_id]:
            if ticket_id not in data.tickets:
                raise NotFound(f"no ticket {ticket_id}")
            return data.ticket(data.tickets[ticket_id])
        case ["tickets"]:
            rows = data.dataset.tickets
            if "status" in q:
                rows = [t for t in rows if t.status.value == q["status"]]
            return [data.ticket(t) for t in rows[:limit]]
        case ["policies"]:
            return sorted(data.policies)
        case ["policies", name]:
            if name not in data.policies:
                raise NotFound(f"no policy {name}")
            return {"name": name, "body": data.policies[name]}
    raise NotFound(f"no route {path}")


def make_handler(data: KestrelData) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "KestrelMock/0.3"

        def do_GET(self) -> None:  # noqa: N802 (http.server naming)
            url = urlparse(self.path)
            try:
                status, payload = 200, route(data, url.path, parse_qs(url.query))
            except NotFound as err:
                status, payload = 404, {"error": str(err)}
            except ValueError as err:
                status, payload = 400, {"error": str(err)}
            body = json.dumps(_json(payload)).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:  # quiet by default
            pass

    return Handler


def make_server(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, seed: int = 2026, scale: float = 1.0
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(KestrelData(generate(seed, scale))))


def serve_in_thread(
    port: int = 0, seed: int = 2026, scale: float = 0.05
) -> tuple[ThreadingHTTPServer, str]:
    """Start the API on a free port in a daemon thread (for tests). Returns (server, base_url)."""
    server = make_server(DEFAULT_HOST, port, seed, scale)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, real_port = server.server_address[:2]
    return server, f"http://{host}:{real_port}"
