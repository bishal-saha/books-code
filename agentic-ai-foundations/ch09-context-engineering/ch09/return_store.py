"""Return authorisations in one SQLite file. The Kestrel mock is read-only, so they live here."""

import sqlite3
import uuid
from contextlib import closing

SCHEMA = """CREATE TABLE IF NOT EXISTS return_authorisations (
    idempotency_key TEXT PRIMARY KEY, ra_id TEXT NOT NULL, order_id TEXT NOT NULL,
    status TEXT NOT NULL, payload TEXT NOT NULL)"""
SELECT = "SELECT ra_id, order_id, status FROM return_authorisations WHERE idempotency_key = ?"


class ReturnStore:
    """Each call opens its own connection, so the store works from any thread."""

    def __init__(self, path: str) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)  # a second writer waits for the lock
        db.execute(SCHEMA)
        return db

    def find(self, key: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute(SELECT, (key,)).fetchone()
        return {"ra_id": row[0], "order_id": row[1], "status": row[2]} if row else None

    def insert_pending(self, key: str, order_id: str, payload: str) -> tuple[bool, dict]:
        """Insert unless the key exists. Returns (inserted, the row stored under the key)."""
        with closing(self._connect()) as db, db:  # closing() closes; `db` commits
            cur = db.execute(
                "INSERT INTO return_authorisations VALUES (?, ?, ?, 'pending', ?) "
                "ON CONFLICT(idempotency_key) DO NOTHING",
                (key, f"RA-{uuid.uuid4().hex[:8].upper()}", order_id, payload),
            )
            ra_id, order_id, status = db.execute(SELECT, (key,)).fetchone()
        return cur.rowcount == 1, {"ra_id": ra_id, "order_id": order_id, "status": status}

    def count(self) -> int:
        with closing(self._connect()) as db:
            return db.execute("SELECT COUNT(*) FROM return_authorisations").fetchone()[0]
