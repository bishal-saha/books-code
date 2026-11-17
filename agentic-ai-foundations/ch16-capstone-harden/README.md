# Chapter 16: Capstone III, Harden

> Code for **[Capstone III, Harden: error handling, cost limits and a small eval suite](https://iambishal.com/resources/books/agentic-ai-foundations/read/capstone-harden-error-handling-cost-limits-eval)**, chapter 16 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter (capstone hardening: failure classes, retries, the money budget, the eval) |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch16.eval` (fake model, no key) |
| Tests | `uv run pytest` (no key, no network: fake model, an offline search service over `httpx.MockTransport`, seeded exports in a temporary folder) |
| Keys | only a live run needs one: copy `.env.example` to `.env` and `models.example.toml` to `models.toml` |

## Run it

```bash
cd books-code/agentic-ai-foundations/ch16-capstone-harden
uv run kestrel up --no-serve                          # writes .kestrel/ (exports, docs)
uv run pytest                                         # 140 tests
uv run python -m ch16.eval                            # 6 golden tasks x 5 trials, fake model
uv run python -m ch16.cli --demo carriers-tight-money # a run stopped by the money budget
```

Expected eval output (fake-model output: scripted replies and token counts, hand-written search
results, illustrative prices of $1 / $5 per million tokens and $0.005 per search request; trials
2 and 4 get a search service whose first request fails with HTTP 503):

```text
[fake model: scripted replies and token counts, hand-written search results,
 illustrative prices; tool results come from the seeded exports]
task                         pass  pass^k  avg cost  max cost  avg steps stop causes
carriers-late-last-quarter   5/5   yes     $0.0223   $0.0253   3.0       finished=5
lost-by-one-carrier          5/5   yes     $0.0075   $0.0075   2.0       finished=5
zero-in-a-covered-month      5/5   yes     $0.0075   $0.0075   2.0       finished=5
quarter-not-covered          5/5   yes     $0.0075   $0.0075   2.0       finished=5
sandbox-probe                5/5   yes     $0.0075   $0.0075   2.0       finished=5
carriers-tight-money         5/5   yes     $0.0156   $0.0156   2.0       cost_limit=5
overall                      30/30 6/6     spent $0.3395 of the $0.50 eval cap, 0 skipped
```

Traces go to `traces/<eval id>/<task id>-t<trial>.jsonl` (Chapter 13's layout). The offline
result is the same on every run by construction: it tests the harness, the checks and the
failure handling, not a model. A live eval, with your key and a priced configuration:

```bash
uv run --env-file .env python -m ch16.eval --live --config hosted-sdk
```

Expected output of `--demo carriers-tight-money` (fake-model output; your trace name differs):

```text
STOPPED: cost_limit (money budget: $0.0156 of $0.0160 spent, too little left for another model call)
PARTIAL, unchecked: no answer was written. Tools returned these locations:
  - https://news.example.com/2025/11/harbour-express-weekend
  - https://reviews.example.com/harbour-express
  - https://reviews.example.com/swiftway-parcel
  - shipments.csv
They are not claims; the trace has every tool result.

Run: cost_limit after 2 steps (answer retries: 0, search requests: 2)
Tokens: 4,800 in / 160 out
Cost: $0.0156 of the $0.0160 budget ($0.0056 model at an illustrative price + $0.0100 search)
Trace: traces/cli/<time>-carriers-tight-money.jsonl
```

New demos: `search-flaky` (one 503, retried, answered), `search-refused` (every search gets
HTTP 401: answered from the exports with `missing`), `model-overloaded` (transient model error
after a count: stopped, try later), `key-rejected` (permanent model error before any tool). All
of Chapter 15's demos still run. Exit codes are Chapter 15's: 0 answered, 3 needs_info,
4 rejected, 5 stopped (`cost_limit` included), 2 bad arguments or configuration.

## What's here

The folder stands alone: it copies `ch15-capstone-build/` forward and changes a few files.

| File | What it shows |
|---|---|
| `ch16/failures.py` | New. `FailureKind` (transient, permanent), `SearchHTTPError`, `classify()`. |
| `ch16/retry.py` | New. `RetryPolicy`, full-jitter `backoff_s`, `retry_call` bounded by attempts and the run's time left. |
| `ch16/budget.py` | Changed. Money in `RunBudget` and `BudgetTracker`, `StopCause.COST_LIMIT`, `describe()`. |
| `ch16/agent.py` | Changed. The money check before each call, the per-call timeout shared with the SDK's retry, `stop_detail`. |
| `ch16/tools.py` | Changed. `search_web` retries transient failures, charges every request, returns one clear error; `{"results": null}` is an error result. |
| `ch16/research.py` | Changed. Prices the run from models.toml; `gathered` for stopped runs. |
| `ch16/cli.py` | Changed. Names the limit, prints the unchecked partial, refuses an unpriced configuration. |
| `ch16/eval.py` | New. Chapter 13's eval over the capstone's golden tasks, with search fees and the most expensive trial. |
| `ch16/offline.py` | New. A pretend search service over the hand-written fixture, through `HttpSearchBackend`. |
| `ch16/golden.py`, `golden_tasks.toml` | Changed. `expected_stop`, a per-task `run_max_cost_usd`, the `carriers-tight-money` task. |
| `ch16/scripted.py` | Changed. Illustrative search price, scripted model errors, the new demos. |
| `ch16/settings.py`, `.env.example` | Changed. `SEARCH_RETRY_*`, `EVAL_TRIALS`, `EVAL_MAX_COST_USD`. |
| `LIMITATIONS.md` | New. What the assistant does not do, and which book picks it up. |
| everything else | Copied from Chapter 15. |

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
