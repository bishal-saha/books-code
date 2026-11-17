# Chapter 12: Agent frameworks landscape

> Code for **[Agent frameworks landscape: when to use one, when to write the loop yourself](https://iambishal.com/resources/books/agentic-ai-foundations/read/agent-frameworks-build-or-adopt)**, chapter 12 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch12.edges`, `uv run python -m ch12.beta_tool_demo`, `uv run python -m ch12.records` (no key) |
| Tests | `uv run pytest` (no key; the Kestrel test starts the mock API itself if it is not running) |
| Keys | None. Every model reply here comes from the fake model. |

No agent framework is installed for this chapter. `beta_tool_demo.py` uses a helper that ships
inside the anthropic SDK the book already pins.

## What's here

The folder stands alone: files marked "copied" come from Chapter 11's folder.

| File | What it shows |
|---|---|
| `ch12/annotated_agent.py` | Chapter 11's `run_agent` (Chapter 7's loop with Chapter 9's inspector hook), unchanged, with `# framework:` comments naming the loop part of each block. |
| `ch12/edges.py` | New. The checklist's edges on our loop, with Chapter 11's read-only tools: an invented argument, an unknown tool and a model that never ends its turn (fake model, real Kestrel tool calls). |
| `ch12/beta_tool_demo.py` | New. The schema `@beta_tool` builds in anthropic 2.8, and what a bad call does. Offline. |
| `ch12/records.py` | New. Checks that every decision record answers the checklist's questions. |
| `checklist.md` | New. The build-or-adopt checklist. |
| `decisions/*.md` | New. Decision records for the three Kestrel requests and the capstone (`capstone.md` goes into the Chapter 14 spec). |
| `ch12/registry.py`, `tools.py`, `model_client.py`, `anthropic_adapter.py`, `openai_compatible_adapter.py`, `fake_model.py`, `budget.py`, `inspector.py`, `context_budget.py`, `results.py`, `truncate.py`, `lookups.py`, `shaping.py`, `settings.py`, `prompts.py` | Copied from Chapter 11 unchanged (imports renamed). |
| `ch12/prompts/ops_agent_v2.md` | Copied from Chapter 8: the operations prompt the edges demo uses. |
| `tests/` | The loop's exits, errors as results, the edges demo against the seeded API, the records and the `@beta_tool` schema. |

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
uv run python -m ch12.edges
uv run python -m ch12.beta_tool_demo
uv run python -m ch12.records
```

## Expected output

`pytest` reports `13 passed`.

`ch12.edges` scripts the model, so every model turn below is fake-model output; the tool
results come from the Kestrel mock API. The clock is fixed (0.2 s per read), so times are the same each run and mean nothing.

```text
== an invented argument, then an unknown tool (fake model)
step 1  tool_call 1x get_delivery_status     in=900    out=40    400 ms
step 2  tool_call 1x get_delivery_status (1 ERR) in=900    out=40    400 ms
step 3  tool_call 1x track_parcel (1 ERR)    in=900    out=40    400 ms
step 4  finished  -                          in=187    out=21    400 ms
stopped: finished  steps 4/4  tokens 3028/20000  time 3.4/60 s
tool result 2: is_error=True Invalid arguments for get_delivery_status. verbose: Extra inputs are not permitted; got True.
tool result 3: is_error=True Unknown tool: track_parcel. Available tools: get_delivery_status, list_shipments, get_ticket, get_policy, get_stock.

== a model that never ends its turn (fake model)
step 1  tool_call 1x get_delivery_status     in=900    out=40    400 ms
step 2  tool_call 1x get_delivery_status     in=900    out=40    400 ms
step 3  tool_call 1x get_delivery_status     in=900    out=40    400 ms
step 4  tool_call 1x get_delivery_status     in=900    out=40    400 ms
stopped: step_limit  steps 4/4  tokens 3760/20000  time 3.4/60 s
answer: ''  (partial result, labelled step_limit)
```

```text
$ uv run python -m ch12.beta_tool_demo
schema from @beta_tool:
{
  "order_or_ticket_id": {
    "description": "The id the user gave: an order id (O-0013833) or a ticket id.",
    "pattern": "^(O-\\d{7}|T-\\d{6})$",
    "title": "Order Or Ticket Id",
    "type": "string"
  }
}
pattern kept: True
call with a bad id raises ValueError: Invalid arguments for function get_delivery_status
```

```text
$ uv run python -m ch12.records
capstone                 hand-written agent loop (run_agent), no agent framework.
expense-claims           no framework; no agent loop.
late-shipments           build (keep run_agent).
return-authorisations    spike, then adopt LangGraph if it passes gates 2 to 5; else build.
4 records, 0 problems
```

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
