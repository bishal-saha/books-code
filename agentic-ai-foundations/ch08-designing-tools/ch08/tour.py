"""A tour of the v2 tools: real calls through the registry, no model, no key.

uv run python -m ch08.tour     # needs the mock API: uv run kestrel up
"""

import os
from datetime import date
from tempfile import TemporaryDirectory

from ch08.lookups import kestrel_client
from ch08.model_client import ToolCall
from ch08.return_store import ReturnStore
from ch08.settings import DEFAULT_KESTREL_URL
from ch08.tools import build_registry

TODAY = date(2025, 12, 16)  # the fixed date the book's examples use
RETURN = {"ticket_id": "T-000410", "reason": "Doesn't fit."}

CALLS = [
    ("get_delivery_status", {"order_or_ticket_id": "T-000281"}),
    ("get_delivery_status", {"order_or_ticket_id": "42"}),
    ("get_ticket", {"ticket_id": "T-999999"}),
    ("list_shipments", {"carrier": "Swiftway Parcel", "late": True, "limit": 500}),
    ("list_shipments", {"carrier": "Swiftway Parcel", "late": True, "limit": 2}),
    ("create_return_authorisation", {**RETURN, "lines": [{"sku": "SKU-00042", "quantity": 2}]}),
    (
        "create_return_authorisation",  # the same return, split across two lines
        {**RETURN, "lines": [{"sku": "SKU-00042", "quantity": 1}] * 2},
    ),
    (
        "create_return_authorisation",  # delivered 2025-11-13: outside the 30-day window
        {
            "ticket_id": "T-000122",
            "lines": [{"sku": "SKU-00007", "quantity": 1}],
            "reason": "Changed my mind.",
        },
    ),
    (
        "create_return_authorisation",  # a trade order: its window depends on a contract
        {
            "ticket_id": "T-000458",
            "lines": [{"sku": "SKU-00105", "quantity": 1}],
            "reason": "No longer needed.",
        },
    ),
]


def main() -> None:
    url = os.environ.get("KESTREL_URL", DEFAULT_KESTREL_URL)
    with kestrel_client(url) as http, TemporaryDirectory() as tmp:
        registry = build_registry(http, ReturnStore(f"{tmp}/returns.sqlite"), TODAY)
        for n, (name, args) in enumerate(CALLS, start=1):
            result = registry.dispatch(ToolCall(id=f"call_{n}", name=name, arguments=args))
            print(f"{name} {args}")
            print(f"  {'ERROR' if result.is_error else 'ok'}: {result.content}\n")


if __name__ == "__main__":
    main()
