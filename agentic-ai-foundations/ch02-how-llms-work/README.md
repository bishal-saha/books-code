# Chapter 2: How LLMs work, just enough

> Code for **[How LLMs work, just enough: tokens, context windows, sampling and reasoning models](https://iambishal.com/resources/books/agentic-ai-foundations/read/how-llms-work-just-enough)**, chapter 2 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · kestrel-outfitters 0.3.0 · last verified 2026-11-18 |
| Run | `uv run --env-file .env python -m ch02.tokens returns-policy.md` |
| Tests | `uv run pytest` (no key, no network) |
| Keys | optional: `ANTHROPIC_API_KEY` in `.env` for counted tokens, the sampling demo and the reasoning comparison |

## What's here

| File | What it shows |
|---|---|
| `ch02/settings.py` | Model, key, prices and window size from environment variables. Prices are `Decimal`. |
| `ch02/tokens.py` | Token count (provider `messages.count_tokens`, or a labelled four-characters-per-token estimate without a key), the context-window check and the CLI. |
| `ch02/cost.py` | Cost from configured per-million prices. |
| `ch02/temperature.py` | A toy sampler over made-up scores: how temperature reshapes next-token probabilities. No model, no key. |
| `ch02/sampling_demo.py` | One question about the returns policy sent N times; distinct answers, truncations, tokens and cost. |
| `ch02/reasoning.py` | One multi-step question at two effort levels with adaptive thinking; output and thinking tokens, latency, cost. |
| `conftest.py` | Puts this folder on `sys.path`; test settings; the seeded docs; `fake_client`, a stand-in for `anthropic.Anthropic`. |
| `tests/fixtures/*.json` | Hand-written responses in the Messages API shape (parsed with the SDK's own `Message` type). Not recordings. |
| `tests/test_live.py` | One live call to `count_tokens`, marked `live` and skipped by default. |

## Run it

From the book folder (`agentic-ai-foundations/`), once:

```bash
uv sync
```

Then from this folder:

```bash
uv run kestrel up --no-serve       # writes .kestrel/ (docs, exports, database); no server needed here
cp .env.example .env               # check model, prices and window against your provider's docs
uv run pytest
uv run --env-file .env python -m ch02.tokens returns-policy.md
uv run python -m ch02.temperature
```

With `ANTHROPIC_API_KEY` set in `.env`:

```bash
uv run --env-file .env python -m ch02.sampling_demo --runs 5
uv run --env-file .env python -m ch02.reasoning --efforts low high
uv run pytest -m live
```

## Expected output

`pytest` reports `23 passed, 1 deselected`. Without a key, the counter prints:

```text
page:                returns-policy.md
characters:          500
heuristic tokens:    125
counted tokens:      -  (ESTIMATE: no API key)
fits the window:     True (max_tokens 1024)  (ESTIMATE: no API key)
input cost (USD):    0.0000125  (ESTIMATE: no API key)
worst case (USD):    0.0005245  (ESTIMATE: no API key)
```

The toy sampler prints:

```text
temperature 0.2:  within 0.99 (99)  up 0.01 (1)  for 0.00 (0)  before 0.00 (0)
temperature 1.0:  within 0.63 (57)  up 0.23 (22)  for 0.09 (15)  before 0.05 (6)
temperature 2.0:  within 0.44 (28)  up 0.27 (35)  for 0.16 (19)  before 0.13 (18)
```

With a key, a `model` line names the configured model, `counted tokens` shows the provider's figure and the cost lines lose the label. The sampling demo and the reasoning comparison need a key; without one they exit with `error: set ANTHROPIC_API_KEY to call the provider`. Their numbers vary from run to run, which is the point of the chapter.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
