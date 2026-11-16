"""The `kestrel` command.

kestrel info                         what the package contains
kestrel up [--dir .kestrel]          workspace folder, then the mock API on http://127.0.0.1:8700
kestrel data --out kestrel.sqlite    only the SQLite database
"""

from __future__ import annotations

import argparse
from pathlib import Path

from kestrel import DISCLAIMER, __version__
from kestrel.cli_support import write_sqlite
from kestrel.data import generate
from kestrel.services import DEFAULT_PORT, make_server
from kestrel.workspace import up


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kestrel", description=DISCLAIMER)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="what the package contains")
    up_cmd = sub.add_parser("up", help="prepare a local workspace (database, exports, docs)")
    up_cmd.add_argument("--dir", type=Path, default=Path(".kestrel"))
    up_cmd.add_argument("--seed", type=int, default=2026)
    up_cmd.add_argument("--scale", type=float, default=1.0)
    up_cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    up_cmd.add_argument("--no-serve", action="store_true", help="only write the workspace")
    data = sub.add_parser("data", help="write the synthetic dataset to SQLite")
    data.add_argument("--out", type=Path, default=Path("kestrel.sqlite"))
    data.add_argument("--seed", type=int, default=2026)
    data.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args(argv)

    if args.command == "info":
        print(f"kestrel-outfitters {__version__}\n{DISCLAIMER}")
        print("Data: customers, employees, products, orders, shipments, tickets, expense claims.")
        print("Docs: shipping, returns and expense policies (one outdated on purpose).")
        print("Mock API: orders, shipments, stock, tickets, policies (kestrel up).")
    elif args.command == "up":
        result = up(args.dir, args.seed, args.scale)
        print(f"Kestrel workspace ready in {args.dir}/")
        print("  kestrel.sqlite: " + ", ".join(f"{k} {v}" for k, v in result["database"].items()))
        print("  exports/: " + ", ".join(f"{k} ({v} rows)" for k, v in result["exports"].items()))
        print("  docs/: " + ", ".join(result["docs"]))
        if not args.no_serve:
            server = make_server(port=args.port, seed=args.seed, scale=args.scale)
            print(f"Mock API on http://127.0.0.1:{args.port} (GET /health). Ctrl+C to stop.")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("\nStopped.")
            finally:
                server.server_close()
    elif args.command == "data":
        counts = write_sqlite(generate(args.seed, args.scale), args.out)
        print(f"Wrote {args.out}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
