# Chapter 5: Structured outputs

> Code for **[Structured outputs: JSON Schema, validation and recovering from bad output](https://iambishal.com/resources/books/agentic-ai-foundations/read/structured-outputs)**, chapter 5 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run python -m ch05.run --demo` (fake model) or `uv run --env-file .env python -m ch05.run [--native]` (real model) |
| Tests | `uv run pytest` (fake model, no key) |
| Keys | `ANTHROPIC_API_KEY` and `MODEL` for the real-model run only (copy `.env.example` to `.env`) |

## What's here

| File | What it shows |
|---|---|
| `ch05/models.py` | `ExpenseClaim`: the output contract as a pydantic model; `python -m ch05.models` prints its JSON Schema. |
| `ch05/extract.py` | `validate_output` (syntax, shape, meaning) and `extract`: stop reason first, then validate-and-retry with feedback, bounded by `max_attempts`. Works with any output model. |
| `ch05/claims.py` | The seven fixture claims (`claims.jsonl`) and `extract_claim`. |
| `ch05/prompts.py`, `ch05/prompts/extract_claim_v1.md` | Chapter 4's prompt loader and six-section layout; the claim goes inside escaped `<data>` tags, the generated schema into the output format. |
| `ch05/policy.py` | Reads `GET /policies/expense-policy` from the mock API and flags claims in plain code. |
| `ch05/run.py` | The batch: extract, check, print Priya's queue. `--demo` uses the scripted replies in `demo_replies.json`. |
| `ch05/anthropic_adapter.py` | Chapter 3's adapter plus `output_format`: native structured output via `output_config.format` and `anthropic.transform_schema`. |
| `ch05/model_client.py`, `fake_model.py`, `settings.py` | Chapter 3's model client, fake model and settings (plus `MAX_EXTRACTION_ATTEMPTS`; `MODEL_THINKING=off`, the default, sends thinking disabled). |
| `ch05/sample_replies.py` | Test data: one valid reply and variants that each break it in one way. |
| `tests/` | Schema and validator tests, validate-and-retry with the fake model, the adapter against a fake HTTP transport, the policy against the seeded API, the demo end to end, two `live` tests. |
| `conftest.py` | Puts this folder on `sys.path`; the `kestrel_url` fixture uses your running server, or starts the same seeded API in the test process. |

## Run it

From the book folder (`agentic-ai-foundations/`), once: `uv sync`. Then from this folder, in one terminal:

```bash
uv run kestrel up          # serves http://127.0.0.1:8700; Ctrl+C to stop
```

and in a second terminal (the tests start the same seeded API themselves if none is running):

```bash
uv run pytest
uv run python -m ch05.models            # the JSON Schema
uv run python -m ch05.run --demo        # scripted fake model, no key
cp .env.example .env                    # then set ANTHROPIC_API_KEY and MODEL
uv run --env-file .env python -m ch05.run           # real model, prompt-only JSON
uv run --env-file .env python -m ch05.run --native  # real model, native structured output
```

## Expected output

`pytest` reports `29 passed, 2 deselected` (the live tests). `run --demo` prints:

```text
claim     category   amount      receipt  attempts  flags
claim-01  meals      142.60 USD  yes      1         OVER_LIMIT
claim-02  travel     48.20 USD   no       1         MISSING_RECEIPT
claim-04  travel     310.00 EUR  yes      2         NEEDS_CONVERSION
claim-05  equipment  64.99 USD   no       1         MISSING_RECEIPT
claim-06  meals      25.00 ?     yes      1         MISSING_DETAILS
claim-03  software   240.00 USD  yes      1         -
claim-07  FAILED: invalid after 3 attempt(s)
10 model calls, 5139 tokens (failed attempts included)
```

The fake model counts words as tokens. A real model's replies vary from run to run, so attempts and failures differ; run it more than once before you compare the two paths.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
