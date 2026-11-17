# Chapter 9: Context engineering basics

> Code for **[Context engineering basics: what goes in the window and why it matters](https://iambishal.com/resources/books/agentic-ai-foundations/read/context-engineering-basics)**, chapter 9 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run python -m ch09.inspect_ops --fake chased` and `uv run python -m ch09.handbook_compare --fake` (no key) |
| Tests | `uv run pytest` (no key; the Kestrel tests start the mock API themselves if it is not running) |
| Keys | `ANTHROPIC_API_KEY`, `MODEL` and prices in `.env` for a run with a real model; see `.env.example` |

## What's here

The folder stands alone: files marked "copied" come from Chapter 8's folder (which took the loop and model client from Chapter 7), with the change noted.

| File | What it shows |
|---|---|
| `ch09/context_budget.py` | New. `ContextBudget`: the enforced tool-result cap and output reserve, warning-only ceilings. |
| `ch09/inspector.py` | New. The context budget inspector: tokens and share per component, `ContextInspector` (the loop hook), `context_table`. |
| `ch09/truncate.py` | New. `ProvenancedResult`, `cap_result` (head and tail, or a page from an offset), `enforce_cap`. |
| `ch09/results.py` | New. `render_tool_result`: the one rendering path for every tool output. |
| `ch09/summarise.py` | New. `summarise_result`, opt-in per tool, with a capped fallback. |
| `ch09/doc_tools.py` | New. `list_docs` and `read_doc` over `.kestrel/docs/`. |
| `ch09/grade.py`, `ch09/questions.py` | New. Grace's policy questions and the simple grader. |
| `ch09/handbook_compare.py` | New. Variant A (whole handbook in the prompt) against variant B (the two doc tools). |
| `ch09/inspect_ops.py` | New. Chapter 8's operations agent (v2 tools, `ops_agent_v2` prompt) with the inspector on. |
| `ch09/demo_cap.py` | New. `read_doc` with a tiny cap, then the page the marker points to. |
| `ch09/prompts/handbook_v1.md`, `docs_agent_v1.md`, `summarise_v1.md` | New prompts (the first two in Chapter 4's six sections). |
| `ch09/model_client.py` | Copied. Adds `count_tokens()`, `provider_counts` and `estimate_tokens()`. |
| `ch09/anthropic_adapter.py` | Copied. `count_tokens()` calls the SDK's `messages.count_tokens` with the same model. |
| `ch09/fake_model.py` | Copied. `count_tokens()` returns a local estimate and counts its calls. |
| `ch09/agent.py` | Copied. `run_agent(..., inspector=)`; the step log gains `context`. |
| `ch09/registry.py` | Copied. Chapter 8's registry; it takes the cap and `dispatch` renders through `render_tool_result` (replaces `as_data`). |
| `ch09/tools.py` | Copied. Chapter 8's v2 tools; `build_registry` takes the cap. |
| `ch09/lookups.py`, `shaping.py`, `returns.py`, `return_store.py`, `paths.py` | Copied unchanged from Chapter 8. |
| `ch09/settings.py` | Copied. Adds `CONTEXT_WINDOW`, `TOOL_RESULT_MAX_CHARS`, the two ceilings and `CHARS_PER_TOKEN`. |
| `ch09/scripted.py` | New. The chased/stuck runs on the v2 tools, plus the handbook comparison's scripted replies. |
| `ch09/budget.py`, `ch09/prompts.py`, `ch09/prompts/ops_agent_v2.md` | Copied unchanged. |
| `tests/` | Inspector, truncation, rendering, summaries, doc tools, the comparison and grader, the adapter's count call, Chapter 7's loop tests and Chapter 8's registry, tools, returns and shaping tests; `test_live.py` needs a key (`-m live`). |

## Run it

From the book folder (`agentic-ai-foundations/`), once:

```bash
uv sync
```

Then from this folder, in one terminal:

```bash
uv run kestrel up          # writes .kestrel/ (docs included), serves http://127.0.0.1:8700
```

and in a second terminal:

```bash
uv run pytest
uv run python -m ch09.inspect_ops --fake chased
uv run python -m ch09.handbook_compare --fake
uv run python -m ch09.demo_cap
cp .env.example .env       # then fill in the key, model, prices and CONTEXT_WINDOW
uv run --env-file .env python -m ch09.inspect_ops O-0014614 O-0004943 O-0004365 O-9999999
uv run --env-file .env python -m ch09.handbook_compare
```

## Expected output

`pytest` reports `90 passed, 1 deselected` (the live test). Fake-model output: the replies (and
the `in=`/`out=` usage on step lines) are scripted; the context table and the comparison's token
counts are local estimates (`CHARS_PER_TOKEN`) of the real requests, Kestrel data included.

```text
$ uv run python -m ch09.inspect_ops --fake chased
[fake model: scripted replies; tool results from the mock API]
step 1  tool_call 4x get_delivery_status (1 ERR) in=1210   out=96    8 ms
step 2  tool_call 1x list_shipments          in=1830   out=58    5 ms
step 3  finished  -                          in=4120   out=162   0 ms
stopped: finished  steps 3/8  tokens 7476/60000  time 0.0/90 s
step         overhead         system          tools        history   tool_results   total  headroom
1              1 (0%)      263 (18%)     1169 (80%)        35 (2%)         0 (0%)    1468     97508
2              1 (0%)      263 (15%)     1169 (66%)        94 (5%)      238 (13%)    1765     97211
3              1 (0%)      263 (11%)     1169 (49%)       113 (5%)      841 (35%)    2387     96589
[local estimates; window 100000, output reserve 1024]
```

```text
$ uv run python -m ch09.handbook_compare --fake
handbook: 4 docs, 2102 chars
[fake model: scripted replies; token counts are local estimates of the real requests]
question              variant  steps  input tokens
trade-late-delivery   A        1      811
trade-late-delivery   B        3      2077
training-over-limit   A        1      803
training-over-limit   B        3      2015
trade-returns         A        1      796
trade-returns         B        3      1977
```

```text
$ uv run python -m ch09.demo_cap
[origin: shipping-policy.md | kind: file | shown: 0-165, 654-725 of 725 chars | truncated]
<data># Shipping policy (v3, effective 1 March 2025)

&gt; Kestrel Outfitters is a fictional company; this document is synthetic.

- Orders placed before 14:00 on a working d
[truncated: chars 165-654 omitted]
r performance is reviewed every quarter by Operations (Tomasz Wójcik).
</data>
[origin: shipping-policy.md | kind: file | shown: 165-465 of 725 chars | truncated]
True
```

With a real model, the replies, steps and counts (then provider counts) vary by model and from
run to run, and `handbook_compare` adds `correct` and `stale` columns. Known refusals:

```text
$ uv run python -m ch09.inspect_ops
inspect_ops.py: error: give order IDs, or --fake chased|stuck
$ uv run python -m ch09.handbook_compare --fake --docs /nonexistent
error: no docs in /nonexistent; run `uv run kestrel up` here first
```

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
