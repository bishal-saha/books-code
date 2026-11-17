# Chapter 15: Capstone II, Build

> Code for **[Capstone II, Build: the agent end to end, with web search, files and citations](https://iambishal.com/resources/books/agentic-ai-foundations/read/capstone-build-agent-web-search-files-citations)**, chapter 15 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter (capstone build: tool bodies, the loop with final-answer checking, the CLI) |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch15.cli --demo carriers-late-last-quarter` (fake model, no key) |
| Tests | `uv run pytest` (no key, no network: fake model, hand-written search results, `httpx.MockTransport`, seeded exports in a temporary folder) |
| Keys | only a live run needs one: copy `.env.example` to `.env` and `models.example.toml` to `models.toml` |

## Run it

```bash
cd books-code/agentic-ai-foundations/ch15-capstone-build
uv run kestrel up --no-serve                                  # writes .kestrel/ (exports, docs)
uv run pytest                                                 # 97 tests
uv run python -m ch15.cli --demo carriers-late-last-quarter   # fake model, no key
```

Expected output (fake-model output: scripted replies and token counts, hand-written search
results and an illustrative price; the counts come from the seeded exports; your trace file
name has the current time in it):

```text
[demo carriers-late-last-quarter: fake-model replies and token counts, hand-written search
 results, an illustrative price; tool results come from the seeded exports]
Question: Which carriers had the most late deliveries last quarter, and what do public sources say about their service?
Today: 2026-01-15

ANSWERED  (confidence: medium)
Harbour Express had the most late deliveries in Q4 2025 (139), then Swiftway Parcel (93). Reviews mention missed delivery windows for Harbour Express and slow busy-season deliveries for Swiftway Parcel.
Claims:
  1. In Q4 2025, Harbour Express had 139 late deliveries and Swiftway Parcel 93, the two highest. [1]
  2. Reviews of Harbour Express mention missed delivery windows on regional routes. [2]
  3. Reviews of Swiftway Parcel describe slow regional deliveries in the busy season. [3]
Citations:
  [1] shipments.csv  (late shipments per carrier, Q4 2025)
  [2] https://reviews.example.com/harbour-express  (reviews of Harbour Express)
  [3] https://reviews.example.com/swiftway-parcel  (reviews of Swiftway Parcel)
Missing: -

Run: finished after 3 steps (answer retries: 0, searches: 2)
Tokens: 8,000 in / 460 out
Cost: $0.0103 model (illustrative price) + search unpriced (SEARCH_USD_PER_QUERY not set)
Trace: traces/cli/<time>-carriers-late-last-quarter.jsonl
```

Other demos: `invented-url-corrected` (one retry fixes a citation), `invented-url-rejected`
(exit 4), `quarter-not-covered` and `sandbox-probe` (needs_info, exit 3), `no-search-partial`
(answered with `missing`), `never-stops` (step_limit, exit 5), `lost-by-one-carrier`,
`zero-in-a-covered-month`.

A live run, with your key and a priced configuration in `models.toml`:

```bash
uv run --env-file .env python -m ch15.cli --today 2026-01-15 \
  "Which carriers had the most late deliveries last quarter, and what do public sources say about their service?"
```

Exit codes: 0 answered, 3 needs_info, 4 rejected, 5 stopped (a budget limit or another
StopCause), 2 bad arguments or configuration.

## What's here

The folder stands alone: it copies Chapter 14's folder forward, plus Chapter 13's loop pieces
and trace and Chapter 10's context policy.

| File | What it shows |
|---|---|
| `ch15/tools.py` | Changed. Chapter 14's four contracts with their bodies: `search_web`, `read_file`, `count_rows`, `calculate` (recursive descent over `Decimal`). `HttpSearchBackend` (illustrative contract), `FixtureSearchBackend`, `UnconfiguredSearch`. |
| `ch15/registry.py` | Changed. Collects the run's citable set from successful, rendered outputs. |
| `ch15/results.py` | Changed. Renders pydantic outputs as JSON fields. |
| `ch15/final.py` | New. `check_final` (validation, then citations) and the one retry message. |
| `ch15/agent.py` | Changed from Chapters 10 and 13. Final-answer checking with one retry, the rejected outcome, the time check after tool calls, a shared `BudgetTracker`. |
| `ch15/research.py` | New. `run_research`: wires tools, prompt, loop and checks; four outcomes. |
| `ch15/cli.py` | New. The command line: outcomes, exit codes, cost line, trace. |
| `ch15/trace.py` | Changed from Chapter 13. Adds context and final-check events; `run_end` from the caller. |
| `ch15/scripted.py` | New. Fake-model scripts for the golden tasks and the demos. |
| `ch15/golden.py` | Changed. Adds `grade()`, deterministic checks of one run against its task. |
| `ch15/settings.py` | Changed. Adds `SEARCH_ENDPOINT` and the context policy settings. |
| `ch15/state.py`, `prompts/compaction_v1.md` | Copied from Chapter 10 (conversation state, trimming, compaction). |
| `ch15/budget.py`, `fake_model.py`, `configs.py`, `anthropic_adapter.py`, `openai_compatible_adapter.py` | Copied from Chapter 13 (`configs.py` now imports `Price` from `pricing.py`). |
| `ch15/answer.py`, `citations.py`, `sandbox.py`, `prompts.py`, `pricing.py`, `truncate.py`, `model_client.py`, `prompts/research_assistant_v1.md` | Copied unchanged from Chapter 14. |
| `spec.md` | Chapter 14's spec with its open questions decided. |
| `golden_tasks.toml`, `fixtures/` | Copied from Chapter 14. The search fixture is hand-written, not a recording. |

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
