# Chapter 1: What "agentic" really means

> Code for **[What "agentic" really means: workflows vs agents and the autonomy spectrum](https://iambishal.com/resources/books/agentic-ai-foundations/read/what-agentic-means-workflows-vs-agents)**, chapter 1 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · httpx 0.28 · pydantic 2.14 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run python -m ch01.order_status T-000407 2025-12-16` |
| Tests | `uv run pytest` |
| Keys | none (this chapter makes no model call) |

## What's here

| File | What it shows |
|---|---|
| `ch01/order_status.py` | A deterministic order-status workflow: ticket → order → shipment → verdict. No model call. |
| `tests/test_mocks_smoke.py` | Smoke test: `/health` and one seeded record from each endpoint the chapter uses. |
| `tests/test_order_status.py` | One test per workflow branch (fake HTTP transport, no server) and one end-to-end run. |
| `conftest.py` | Puts this folder on `sys.path`; the `kestrel_url` fixture uses your running server, or starts the same seeded API in the test process. |

## Run it

From the book folder (`agentic-ai-foundations/`), once:

```bash
uv sync
```

Then from this folder, in one terminal:

```bash
uv run kestrel up          # writes .kestrel/ and serves http://127.0.0.1:8700; Ctrl+C to stop
```

and in a second terminal:

```bash
curl http://127.0.0.1:8700/health
uv run pytest
uv run python -m ch01.order_status T-000407 2025-12-16
```

## Expected output

`curl` prints `{"status": "ok"}`. `pytest` reports `19 passed`. The workflow prints:

```json
{
  "ticket_id": "T-000407",
  "order_id": "O-0006066",
  "carrier": "Swiftway Parcel",
  "shipment_status": "in_transit",
  "promised_by": "2025-12-05",
  "verdict": "late",
  "next_step": "Apologise, share tracking and open a carrier trace."
}
```

With the date `2025-12-03` the same ticket is `on_time`. Known refusals (exit status 1):

```text
$ uv run python -m ch01.order_status NO-SUCH-TICKET 2025-12-16
error: TicketNotFound('no ticket NO-SUCH-TICKET')
$ uv run python -m ch01.order_status T-000007 2025-12-16
error: NoOrderOnTicket('T-000007')
$ uv run python -m ch01.order_status T-000009 2025-12-16
error: NotShipped('order O-0012769 has not shipped')
```

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
