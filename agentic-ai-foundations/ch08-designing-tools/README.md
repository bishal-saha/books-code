# Chapter 8: Designing good tools

> Code for **[Designing good tools: naming, descriptions, errors, idempotency and granularity](https://iambishal.com/resources/books/agentic-ai-foundations/read/designing-good-tools)**, chapter 8 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run python -m ch08.tour` and `uv run python -m ch08.selection_check --fake` (no key) |
| Tests | `uv run pytest` (no key; the Kestrel tests start the mock API themselves if it is not running) |
| Keys | `ANTHROPIC_API_KEY` and `MODEL` in `.env` for the live selection check; see `.env.example` |

## What's here

The folder stands alone: files marked "copied" come from Chapter 7's folder.

| File | What it shows |
|---|---|
| `ch08/registry.py` | Copied from Chapter 7's `tools.py` (the `Tool`, `ToolRegistry`, `ToolError`, `as_data`), with two changes: per-field `hints`, and one line per invalid field in validation errors. |
| `ch08/tools_v1.py` | The "before" set: Chapter 7's `get_order`, `get_shipment`, `list_shipments` unchanged, plus first-draft `get_ticket` and `get_policy`. |
| `ch08/tools.py` | New. The v2 set: `get_delivery_status` (merged), `list_shipments`, `get_ticket`, `get_policy`, their input models, descriptions and `build_registry`. |
| `ch08/returns.py` | New. `create_return_authorisation`: derived idempotency key, business rules that fail closed. |
| `ch08/return_store.py` | New. `ReturnStore`, return authorisations in one SQLite file. |
| `ch08/lookups.py` | New. The Kestrel client (5 s timeout per request phase), ticket-to-order and policy look-ups. |
| `ch08/shaping.py` | New. `truncate` (with a marker) and `paginate` (with a cursor). |
| `ch08/paths.py` | New. `resolve_inside`, the path check Chapter 14 turns into the file sandbox. |
| `ch08/selection_check.py`, `selection_fixture.jsonl` | New. The selection check: acceptable first calls per tool set, and tool calls to an answer. |
| `ch08/scripted.py` | New. The scripted fake model behind `selection_check --fake`. |
| `ch08/tour.py` | New. Real calls to the v2 tools through the registry, no model. |
| `ch08/prompts/ops_agent_v2.md` | New version of Chapter 7's prompt, same six sections; covers tickets, policies and returns. |
| `ch08/agent.py`, `budget.py`, `model_client.py`, `anthropic_adapter.py`, `fake_model.py`, `settings.py`, `prompts.py` | Copied from Chapter 7 unchanged (imports renamed; `agent.py` imports the registry from `registry.py`). |
| `tests/` | Registry, tools, shaping, returns and selection tests on the fake model and the seeded API; `test_live.py` runs only with `-m live`. |

## Run it

From the book folder (`agentic-ai-foundations/`), once:

```bash
uv sync
```

Then from this folder, in one terminal:

```bash
uv run kestrel up          # serves http://127.0.0.1:8700; Ctrl+C to stop
```

and in a second terminal:

```bash
uv run pytest
uv run python -m ch08.tour
uv run python -m ch08.selection_check --fake
cp .env.example .env       # then fill in the key, model and prices
uv run --env-file .env python -m ch08.selection_check --runs 5
```

## Expected output

`pytest` reports `39 passed, 1 deselected` (the live test).

`ch08.tour` calls the tools directly, so every result is real Kestrel data (the `RA-` id is
random on each run):

```text
get_delivery_status {'order_or_ticket_id': 'T-000281'}
  ok: <data>{"order_id": "O-0013833", "order_status": "delivered", "carrier": "Harbour Express", "shipment_status": "delivered", "promised_by": "2025-06-24T21:44:18+00:00", "delivered_at": "2025-06-27T21:44:18+00:00", "late": true}</data>
get_delivery_status {'order_or_ticket_id': '42'}
  ERROR: Invalid arguments for get_delivery_status. order_or_ticket_id: String should match pattern '^(O-\d{7}|T-\d{6})$'; got '42'. Use O- and 7 digits or T- and 6 digits.
get_ticket {'ticket_id': 'T-999999'}
  ERROR: No ticket T-999999. Ticket ids look like T-000281; check the id the user gave. For an order id, use get_delivery_status.
list_shipments {'carrier': 'Swiftway Parcel', 'late': True, 'limit': 500}
  ERROR: Invalid arguments for list_shipments. limit: Input should be less than or equal to 50; got 500.
list_shipments {'carrier': 'Swiftway Parcel', 'late': True, 'limit': 2}
  ok: <data>{"items": [{"shipment_id": "S-0000067", "order_id": "O-0000071", "carrier": "Swiftway Parcel", "status": "delivered", "promised_by": "2025-05-25T23:32:46+00:00", "delivered_at": "2025-05-29T08:32:46+00:00", "late": true}, {"shipment_id": "S-0000083", "order_id": "O-0000089", "carrier": "Swiftway Parcel", "status": "delivered", "promised_by": "2025-08-22T05:28:24+00:00", "delivered_at": "2025-08-26T04:28:24+00:00", "late": true}], "next_cursor": "2", "total": 397, "total_is_capped": false, "applied_filters": {"carrier": "Swiftway Parcel", "late": "true"}}</data>
create_return_authorisation {'ticket_id': 'T-000410', 'reason': "Doesn't fit.", 'lines': [{'sku': 'SKU-00042', 'quantity': 2}]}
  ok: <data>{"ra_id": "RA-A7F28A6A", "order_id": "O-0013196", "status": "pending", "already_existed": false}</data>
create_return_authorisation {'ticket_id': 'T-000410', 'reason': "Doesn't fit.", 'lines': [{'sku': 'SKU-00042', 'quantity': 1}, {'sku': 'SKU-00042', 'quantity': 1}]}
  ok: <data>{"ra_id": "RA-A7F28A6A", "order_id": "O-0013196", "status": "pending", "already_existed": true}</data>
create_return_authorisation {'ticket_id': 'T-000122', 'lines': [{'sku': 'SKU-00007', 'quantity': 1}], 'reason': 'Changed my mind.'}
  ERROR: Order O-0015215's 30-day return window closed on 2025-12-13.
create_return_authorisation {'ticket_id': 'T-000458', 'lines': [{'sku': 'SKU-00105', 'quantity': 1}], 'reason': 'No longer needed.'}
  ERROR: The return window for order O-0007124 can't be confirmed from the order and the returns policy. Don't retry; tell the user a person will review the return.
```

The fake selection check's tool choices and token counts are scripted; it shows the report's
format, not how a real model behaves. The tool results are real.

```text
$ uv run python -m ch08.selection_check --fake
[fake model: scripted tool choices; tool results from Kestrel]
runs per request: 1
set  acceptable first calls  tool calls to answer
v1     5/5                     2.0
v2     6/6                     1.0
```

With a key, the same command without `--fake` runs the live check; its counts vary by model
and from run to run.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
