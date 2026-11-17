# Chapter 14: Capstone I, Design

> Code for **[Capstone I, Design: Kestrel's research assistant (spec, tools, loop)](https://iambishal.com/resources/books/agentic-ai-foundations/read/capstone-design-research-assistant)**, chapter 14 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter (capstone design: contracts, checks and test plan; tool bodies arrive in Chapter 15) |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch14.design_check --today 2026-01-15` (local files only) |
| Tests | `uv run pytest` (no key, no network: the seeded exports are written to a temporary folder) |
| Keys | none in this chapter; `.env.example` lists what Chapter 15 needs |

## Run it

```bash
cd books-code/agentic-ai-foundations/ch14-capstone-design
uv run kestrel up --no-serve                         # writes .kestrel/ (exports, docs, database)
uv run pytest                                        # 44 tests
uv run python -m ch14.design_check --today 2026-01-15
```

Expected output of `design_check` (token figures are local estimates: characters / `CHARS_PER_TOKEN`):

```text
1. Can the model read a quarter of shipments?
   shipments.csv: 18,000 rows, 2,576,661 chars
   last quarter (2025-10-01 to 2026-01-01, by shipped_at): 4,421 rows, 633,018 chars
   = 106 read_file pages of 6,000 chars
2. Fixed part of every call (local estimate)
   system prompt: 3,997 chars, tool definitions: 4,038 chars
   = about 2,009 tokens per call
   5 search results at their caps: 5,205 chars (fits under 16,000)
   10 search results at their caps: 10,410 chars (fits under 16,000)
3. Carrier question walk-through (assumes 500 output tokens per step)
   happy path: 3 steps, 10,227 in + 1,500 out = 11,727
   with a retry: 4 steps, 16,463 in + 2,000 out = 18,463
   with a page read, an error and a retry: 6 steps, 32,781 in + 3,000 out = 35,781
   budget: 8 steps, 60,000 tokens
4. Money for the worse run
   needs a priced 'hosted-sdk' in models.toml and SEARCH_USD_PER_QUERY
```

For section 4, copy `models.example.toml` to `models.toml` and fill in your model's price with its date and source page (Chapter 11's format, the book's one price source), and set `SEARCH_USD_PER_QUERY` in `.env`. It then prints the worse run's cost next to `RUN_MAX_COST_USD`.

## What's here

The folder stands alone. Chapters 15 and 16 copy it forward and fill in the stubs.

| File | What it shows |
|---|---|
| `spec.md` | New. Requirements, non-goals, autonomy placement, definitions, limitations, open questions, security model. |
| `ch14/tools.py` | New. The four tool contracts (`search_web`, `read_file`, `count_rows`, `calculate`): input models, output shapes, descriptions, `SearchBackend`, `build_registry`. Bodies raise `NotImplementedError` until Chapter 15. |
| `ch14/sandbox.py` | New. `resolve_in_sandbox` and `sandbox_name`: the file sandbox. |
| `ch14/answer.py` | New. `FinalAnswer`, `Claim`, `Citation` and their validators. |
| `ch14/citations.py` | New. `citable_locations`, `normalise_url`, `check_citations`. |
| `ch14/golden.py` | New. The golden-task format and `resolve_count`, which computes expected counts with the `csv` module. |
| `ch14/design_check.py` | New. Measures the exports, the fixed prompt and tool size, and the budget walk-through. |
| `ch14/prompts/research_assistant_v1.md` | New. The system prompt, in Chapter 4's six sections. |
| `ch14/prompts.py` | Copied from Chapter 13; adds `build_system_prompt`. |
| `ch14/pricing.py`, `models.example.toml` | Copied from Chapter 13 (`Price`, `cost_of`); adds `load_price`, which reads one configuration's price from Chapter 11's `models.toml`. |
| `ch14/settings.py` | Copied from Chapter 13, trimmed; adds the capstone budget, `RUN_MAX_COST_USD`, the search settings and `EXPORTS_DIR`. |
| `ch14/registry.py`, `results.py`, `truncate.py`, `model_client.py` | Copied unchanged (registry from Chapter 9, the rest from Chapter 13). |
| `golden_tasks.toml` | New. Five golden tasks; `tests/test_golden.py` pins their counts against the seeded data. |
| `fixtures/search/carriers.json` | New. Hand-written search results for the fake backend (invented; example.com URLs). |
| `fixtures/answers/*.json` | New. Example answers the tests validate (written by hand, not model output). |
