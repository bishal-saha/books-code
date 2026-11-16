"""Helpers shared by the CLI and the workspace builder."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from kestrel.data import Dataset


def _value(v: object) -> object:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (tuple, list)):
        return json.dumps([asdict(x) if is_dataclass(x) else x for x in v], default=str)
    return v


def write_sqlite(dataset: Dataset, path: Path) -> dict[str, int]:
    """One table per entity; nested lists (order lines, messages) stored as JSON."""
    path.unlink(missing_ok=True)
    counts: dict[str, int] = {}
    with sqlite3.connect(path) as db:
        for table in fields(Dataset):
            rows = getattr(dataset, table.name)
            columns = [f.name for f in fields(rows[0])]
            db.execute(f"CREATE TABLE {table.name} ({', '.join(columns)})")
            db.executemany(
                f"INSERT INTO {table.name} VALUES ({', '.join('?' for _ in columns)})",
                [tuple(_value(getattr(r, c)) for c in columns) for r in rows],
            )
            counts[table.name] = len(rows)
    return counts
