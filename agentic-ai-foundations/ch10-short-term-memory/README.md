# Chapter 10: Short-term memory

> Code for **[Short-term memory: conversation state, summarisation and compaction](https://iambishal.com/resources/books/agentic-ai-foundations/read/short-term-memory)**, chapter 10 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch10.demo` and `uv run python -m ch10.demo --strategy trim` (no key) |
| Tests | `uv run pytest` (no key; the loop tests start the mock API themselves if it is not running) |
| Keys | none for anything in this folder; `.env.example` lists the settings, the context policy included |

## What's here

The folder stands alone: files marked "copied" come from Chapter 9's folder, with the change noted.

| File | What it shows |
|---|---|
| `ch10/state.py` | New. `ConversationState`, units, `check_pairing`, `cut_points`, `trim_to_target`, `ContextPolicy`, `compact` and its fallback. |
| `ch10/agent.py` | Copied. `run_agent` takes and returns a `ConversationState`; `manage_context` runs before every model call; each step record carries a `context` event. The inspector hook is left out. |
| `ch10/prompts/compaction_v1.md` | New. The summary call's prompt, in Chapter 4's six sections. |
| `ch10/prompts/support_agent_v1.md` | New. Maya's support assistant, in the same six sections. |
| `ch10/scripted.py` | New. Maya's four-question session for the fake model, plus the scripted summary. |
| `ch10/demo.py` | New. Runs that session through the loop against the mock API, with `compact` or `trim`. |
| `ch10/histories.py` | New. Hand-built histories (fixture text, not Kestrel records) for the unit tests and exercises. |
| `ch10/settings.py` | Copied. Adds `CONTEXT_STRATEGY`, `TRIM_TARGET_TOKENS`, `COMPACTION_THRESHOLD_TOKENS`, `COMPACTION_KEEP_UNITS`, `COMPACTION_MAX_TOKENS` and `context_policy()`. |
| `ch10/tools.py` | Copied. Adds `get_ticket` and `get_policy`. |
| `ch10/model_client.py`, `fake_model.py`, `anthropic_adapter.py`, `budget.py`, `prompts.py`, `results.py`, `truncate.py` | Copied unchanged. |
| `tests/` | `test_pairing.py` (check_pairing's own cases, trimming), `test_compaction.py` (summary, cost, fallbacks), `test_agent.py` (the session against the mock API, the new exits), `test_adapter.py` (Chapter 9's adapter tests). |

## Run it

From the book folder (`agentic-ai-foundations/`), once:

```bash
uv sync
```

Then from this folder:

```bash
uv run pytest
uv run python -m ch10.demo
uv run python -m ch10.demo --strategy trim
```

The demo uses the server from `uv run kestrel up` if one is running, and otherwise starts the same
seeded data inside the process.

## Expected output

`pytest` reports `27 passed`. Fake-model output: the replies and the summary are scripted; the tool
results come from the mock API, and the token figures are local `CHARS_PER_TOKEN` estimates of the
real requests.

```text
$ uv run python -m ch10.demo
[fake model: scripted replies; tool results from the mock API; compact]
turn 1 step 1  history     8 tokens  1x get_ticket
turn 1 step 2  history   148 tokens  reply
turn 1 stopped: finished
turn 2 step 1  history   192 tokens  1x get_order, 1x get_shipment
turn 2 step 2  history   377 tokens  reply
turn 2 stopped: finished
turn 3 step 1  history   443 tokens  2x get_policy
turn 3 step 2  history   821 tokens  reply
turn 3 stopped: finished
turn 4 step 1  history   908 tokens  1x list_shipments
turn 4 step 2  history   965 tokens  reply
    compaction: compacted, 8 units summarised, 1678 -> 965 tokens
turn 4 stopped: finished
compactions: 1  summary kept: True
```

```text
$ uv run python -m ch10.demo --strategy trim
...
turn 4 step 1  history   908 tokens  1x list_shipments
turn 4 step 2  history  1251 tokens  reply
    trim: dropped 5 units, 1678 -> 1251 tokens
turn 4 stopped: finished
compactions: 0  summary kept: False
```

## Licence

MIT, like the rest of this repository.
