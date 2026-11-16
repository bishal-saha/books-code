import sqlite3

from kestrel import DISCLAIMER
from kestrel.cli import write_sqlite
from kestrel.data import generate


def test_same_seed_same_rows() -> None:
    assert generate(seed=7, scale=0.02) == generate(seed=7, scale=0.02)


def test_different_seed_different_rows() -> None:
    assert generate(seed=7, scale=0.02).customers != generate(seed=8, scale=0.02).customers


def test_scale_controls_size() -> None:
    small = generate(scale=0.01)
    assert len(small.customers) == 50
    assert len(small.orders) == 200


def test_references_are_valid() -> None:
    d = generate(scale=0.02)
    customer_ids = {c.id for c in d.customers}
    skus = {p.sku for p in d.products}
    employee_ids = {e.id for e in d.employees}
    order_ids = {o.id for o in d.orders}
    assert all(o.customer_id in customer_ids for o in d.orders)
    assert all(line.sku in skus for o in d.orders for line in o.lines)
    assert all(t.customer_id in customer_ids for t in d.tickets)
    assert all(t.order_id is None or t.order_id in order_ids for t in d.tickets)
    assert all(c.employee_id in employee_ids for c in d.claims)


def test_naming_rules() -> None:
    d = generate(scale=0.05)
    assert not any("kestrel" in p.name.lower() for p in d.products)
    assert all(c.email.endswith("@example.com") for c in d.customers)
    assert "fictional" in DISCLAIMER


def test_write_sqlite(tmp_path) -> None:
    path = tmp_path / "k.sqlite"
    counts = write_sqlite(generate(scale=0.01), path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM orders").fetchone()[0] == counts["orders"]
