"""The `kestrel` command.

kestrel info                       what the package contains
kestrel data --out kestrel.sqlite  write the synthetic dataset to SQLite
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from kestrel import DISCLAIMER, __version__
from kestrel.data import Dataset, generate


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kestrel", description=DISCLAIMER)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="what the package contains")
    data = sub.add_parser("data", help="write the synthetic dataset to SQLite")
    data.add_argument("--out", type=Path, default=Path("kestrel.sqlite"))
    data.add_argument("--seed", type=int, default=2026)
    data.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args(argv)

    if args.command == "info":
        print(f"kestrel-outfitters {__version__}\n{DISCLAIMER}")
        print("Data: customers, employees, products, orders, tickets, expense claims.")
        print("Services (CRM, ticketing, finance, orders, docs) arrive with the capstones.")
    elif args.command == "data":
        counts = write_sqlite(generate(args.seed, args.scale), args.out)
        print(f"Wrote {args.out}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
