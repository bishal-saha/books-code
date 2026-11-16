"""`kestrel up`: prepare a local Kestrel Outfitters workspace.

Writes, into one folder (default `.kestrel/`):

- `kestrel.sqlite`: every table of the synthetic dataset
- `exports/*.csv`: flat CSV exports, the kind of files an analyst would be sent
- `docs/*.md`: internal documents (policies, one deliberately outdated)

Book examples point their file tools at this folder. The mock services (CRM,
ticketing, finance) are added by the books that need them.
"""

from __future__ import annotations

import csv
import shutil
from importlib.resources import files
from pathlib import Path

from kestrel.cli_support import write_sqlite
from kestrel.data import Dataset, generate


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> int:
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def write_exports(dataset: Dataset, folder: Path) -> dict[str, int]:
    folder.mkdir(parents=True, exist_ok=True)
    counts = {}
    counts["orders.csv"] = _write_csv(
        folder / "orders.csv",
        ["order_id", "customer_id", "placed_at", "status", "currency", "total"],
        [
            [
                o.id,
                o.customer_id,
                o.placed_at.isoformat(),
                o.status.value,
                o.currency,
                f"{o.total_cents / 100:.2f}",
            ]
            for o in dataset.orders
        ],
    )
    counts["shipments.csv"] = _write_csv(
        folder / "shipments.csv",
        [
            "shipment_id",
            "order_id",
            "carrier",
            "warehouse",
            "shipped_at",
            "promised_by",
            "delivered_at",
            "status",
            "late",
        ],
        [
            [
                s.id,
                s.order_id,
                s.carrier,
                s.warehouse,
                s.shipped_at.isoformat(),
                s.promised_by.isoformat(),
                s.delivered_at.isoformat() if s.delivered_at else "",
                s.status.value,
                "yes" if s.late else "no",
            ]
            for s in dataset.shipments
        ],
    )
    counts["tickets.csv"] = _write_csv(
        folder / "tickets.csv",
        ["ticket_id", "customer_id", "order_id", "channel", "priority", "status", "subject"],
        [
            [
                t.id,
                t.customer_id,
                t.order_id or "",
                t.channel,
                t.priority.value,
                t.status.value,
                t.subject,
            ]
            for t in dataset.tickets
        ],
    )
    counts["products.csv"] = _write_csv(
        folder / "products.csv",
        ["sku", "name", "category", "price", "active"],
        [
            [p.sku, p.name, p.category, f"{p.price_cents / 100:.2f}", p.active]
            for p in dataset.products
        ],
    )
    counts["expense_claims.csv"] = _write_csv(
        folder / "expense_claims.csv",
        [
            "claim_id",
            "employee_id",
            "submitted_at",
            "category",
            "amount",
            "currency",
            "has_receipt",
            "status",
        ],
        [
            [
                c.id,
                c.employee_id,
                c.submitted_at.isoformat(),
                c.category,
                f"{c.amount_cents / 100:.2f}",
                c.currency,
                c.has_receipt,
                c.status.value,
            ]
            for c in dataset.claims
        ],
    )
    return counts


def copy_docs(folder: Path) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    names = []
    for doc in files("kestrel.docs").iterdir():
        if doc.name.endswith(".md"):
            shutil.copyfile(str(doc), folder / doc.name)
            names.append(doc.name)
    return sorted(names)


def up(root: Path, seed: int = 2026, scale: float = 1.0) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    dataset = generate(seed, scale)
    return {
        "database": write_sqlite(dataset, root / "kestrel.sqlite"),
        "exports": write_exports(dataset, root / "exports"),
        "docs": copy_docs(root / "docs"),
    }
