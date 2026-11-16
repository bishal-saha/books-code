# Chapter 7: The agent loop

> Code for **[The agent loop: perceive, reason, act, observe, stop](https://iambishal.com/resources/books/agentic-ai-foundations/read/agent-loop)**, chapter 7 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run python -m ch07.ops_agent --fake chased` (no key) |
| Tests | `uv run pytest` (no key; the Kestrel tests start the mock API themselves if it is not running) |
| Keys | `ANTHROPIC_API_KEY` and `MODEL` in `.env` for a live run and the live test; see `.env.example` |

## What's here

The folder stands alone: files marked "copied" come from Chapter 6's folder, with the one change noted.

| File | What it shows |
|---|---|
| `ch07/budget.py` | New. `StopCause`, `RunBudget` (steps, tokens, wall time), `CallLimits`, `BudgetTracker`. |
| `ch07/agent.py` | New. `run_agent`, `RunResult`, the step log (`StepRecord`, `ToolCallRecord`) and `print_steps`. |
| `ch07/ops_agent.py` | New. The operations agent CLI: live with a key, or `--fake chased` / `--fake stuck`. |
| `ch07/scripted.py` | New. Scripted fake-model runs; the tool results still come from the Kestrel API. |
| `ch07/prompts/ops_agent_v1.md` | New. The system prompt, in Chapter 4's six sections. |
| `ch07/model_client.py` | Copied. `complete()` gains an optional per-call `timeout`. |
| `ch07/anthropic_adapter.py` | Copied. Passes that `timeout` to `messages.create`. |
| `ch07/fake_model.py` | Copied. Records the `timeout` of every call. |
| `ch07/tools.py` | Copied. Adds `list_shipments` and reports tool timeouts as worth one retry. |
| `ch07/settings.py` | Copied. Adds `RUN_MAX_STEPS`, `RUN_MAX_TOKENS`, `RUN_MAX_SECONDS`; `MAX_RETRIES` defaults to 1. |
| `ch07/prompts.py` | Copied unchanged: the versioned prompt loader. |
| `tests/test_agent.py` | Every stop cause, the step log, the shrinking timeout and tool failures as results, on a fake model with in-memory tools. |
| `tests/test_budget.py` | `BudgetTracker` on its own. |
| `tests/test_tools.py` | `list_shipments` against the seeded API; the timeout branch offline. |
| `tests/test_adapter.py` | The per-call timeout reaches the SDK request (fake HTTP transport). |
| `tests/test_ops_agent.py` | Both scripted runs end to end against the seeded API. |
| `tests/test_live.py` | One live run (`-m live`, needs a key). |

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
uv run python -m ch07.ops_agent --fake chased
uv run python -m ch07.ops_agent --fake stuck
cp .env.example .env       # then fill in the key, model and prices
uv run --env-file .env python -m ch07.ops_agent O-0014614 O-0004943 O-0004365 O-9999999
```

## Expected output

`pytest` reports `23 passed, 1 deselected` (the live test). The fake model's replies and token
counts are scripted; the tool results are real. Durations vary.

```text
$ uv run python -m ch07.ops_agent --fake chased
[fake model: scripted replies and token counts; tool results from Kestrel]
step 1  tool_call 4x get_order (1 ERR)       in=1210   out=96    4 ms
step 2  tool_call 2x get_shipment            in=1830   out=70    1 ms
step 3  tool_call 1x list_shipments          in=2690   out=58    3 ms
step 4  finished  -                          in=4120   out=162   0 ms
stopped: finished  steps 4/8  tokens 10236/60000  time 0.0/90 s
O-0014614: the order record says delivered, but its Northline Freight shipment is lost (flagged late, promised 2025-04-18).
O-0004943: shipped; Swiftway Parcel, in transit, not flagged late (promised 2025-12-22).
O-0004365: placed on 2025-06-04 and not shipped yet (promised 2025-06-07).
NEEDS INFO: O-9999999 does not exist in the order system; please check the ID.
Northline Freight has other late shipments: all 10 that the list returned were delivered late.
Carrier trace needed: O-0014614 (Northline Freight).
```

```text
$ uv run python -m ch07.ops_agent --fake stuck
[fake model: scripted replies and token counts; tool results from Kestrel]
step 1  tool_call 1x get_order (1 ERR)       in=900    out=40    2 ms
...
step 8  tool_call 1x get_order (1 ERR)       in=900    out=40    1 ms
stopped: step_limit  steps 8/8  tokens 7520/60000  time 0.0/90 s
```

A live run's steps, wording and token counts vary by model and from run to run; the data does
not. Known refusals:

```text
$ uv run python -m ch07.ops_agent
ops_agent.py: error: give order IDs, or --fake chased|stuck
$ uv run --env-file .env python -m ch07.ops_agent O-0014614     # with no key in .env
error: set ANTHROPIC_API_KEY in .env (or use --fake)
```

If the mock API is not running, every tool call comes back as an error result
(`get_order failed (ConnectError).`, with the traceback logged to stderr) and the run still
ends with a named cause.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
