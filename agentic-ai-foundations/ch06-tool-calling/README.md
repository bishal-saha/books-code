# Chapter 6: Tool calling from first principles

> Code for **[Tool calling from first principles: schemas, the call/result cycle and parallel calls](https://iambishal.com/resources/books/agentic-ai-foundations/read/tool-calling-from-first-principles)**, chapter 6 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run python -m ch06.round_trip --fake single` (no key) |
| Tests | `uv run pytest` (fake model, no key) |
| Keys | `ANTHROPIC_API_KEY`, `MODEL` and prices in `.env` for live runs only; see `.env.example` |

## What's here

| File | What it shows |
|---|---|
| `ch06/tools.py` | `OrderIdArgs`, the `get_order` and `get_shipment` tools (httpx calls to the Kestrel API), `ToolError`, `Tool`, `ToolRegistry` with `definitions()` and `dispatch()`, `build_registry()`. |
| `ch06/model_client.py` | Chapter 3's model client plus `ToolDefinition`, `ToolCall`, `ToolResult`, `ToolChoice`, and the `assistant_message()` / `tool_results_message()` helpers. |
| `ch06/anthropic_adapter.py` | Chapter 3's adapter plus tools: tool definitions, `tool_choice`, `tool_use` blocks in, `tool_result` blocks out. The only file that imports the SDK. |
| `ch06/fake_model.py` | Chapter 3's fake model; scripted responses can carry tool calls, and every request is recorded with its tools and tool choice. |
| `ch06/prompts/order_lookup_v1.md`, `ch06/prompts.py` | The six-section system prompt and Chapter 4's loader. |
| `ch06/round_trip.py` | `needs_tools()` and `run_round_trip()`: one model call, dispatch, one follow-up call. |
| `ch06/scripted.py` | The fake-model scripts for `--fake single` and `--fake parallel`. |
| `ch06/tool_choice_demo.py` | The `tool_choice` each mode sends (`--show`), or one live call per mode. |
| `ch06/settings.py` | Chapter 3's settings, unchanged. |
| `tests/` | Registry and dispatcher, the round trip on the fake model, the adapter against a fake HTTP transport, one `live` test. |

## Run it

From the book folder (`agentic-ai-foundations/`), once: `uv sync`. Then from this folder, in one terminal:

```bash
uv run kestrel up          # writes .kestrel/ and serves http://127.0.0.1:8700; Ctrl+C to stop
```

and in a second terminal:

```bash
uv run pytest
uv run python -m ch06.round_trip --fake single
uv run python -m ch06.round_trip --fake single --wire
uv run python -m ch06.round_trip --fake parallel
uv run python -m ch06.tool_choice_demo --show
cp .env.example .env       # add your key and a current model from your provider
uv run --env-file .env python -m ch06.round_trip "Is order O-0000141 still open?"
uv run --env-file .env python -m ch06.tool_choice_demo
uv run --env-file .env pytest -m live
```

## Expected output

`pytest` reports `27 passed, 1 deselected` (the deselected one is the live test).

`--fake` runs use scripted model replies (labelled as fake); the tool results are real rows from
the seeded API, so they match on every machine. `round_trip --fake single`:

```text
[fake model: scripted replies; the tool results come from the Kestrel API]
-- model call 1 (messages: 1)
stop reason: tool_call
text: I'll look up order O-0000141.
tool call: {"id": "toolu_fake_01", "name": "get_order", "arguments": {"order_id": "O-0000141"}}
result for toolu_fake_01 (is_error=False): <data>{"order_id": "O-0000141", "customer_id": "C-001755", "channel": "trade", "placed_at": "2025-10-09T07:29:46+00:00", "status": "shipped", "currency": "EUR", "total": 54121.99, "promised_date": "2025-10-11"}</data>
-- model call 2 (messages: 3)
stop reason: finished
text: O-0000141 is still open: it has shipped but is not delivered yet (promised 2025-10-11).
```

`tool_choice_demo --show`:

```text
allow (auto)               -> {"type": "auto"}
require (required)         -> {"type": "any"}
require get_order (tool)   -> {"type": "tool", "name": "get_order"}
forbid (none)              -> {"type": "none"}
allow, one call at most    -> {"type": "auto", "disable_parallel_tool_use": true}
```

Live runs depend on your model: its wording varies, and some current models reject the forced
modes (`any`, `tool`); the demo then prints `error: the provider rejected the request: ...` for
that mode and carries on.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
