# Chapter 3: Talking to models

> Code for **[Talking to models: APIs, messages, system prompts and streaming](https://iambishal.com/resources/books/agentic-ai-foundations/read/talking-to-models)**, chapter 3 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-16 |
| Run | `uv run --env-file .env python -m ch03.draft_reply T-000407` |
| Tests | `uv run pytest` (no key, no network) |
| Keys | `ANTHROPIC_API_KEY` in `.env` for the CLI, `first_call.py` and the live tests; see `.env.example` |

## What's here

| File | What it shows |
|---|---|
| `ch03/settings.py` | `Settings`: model, key, prices (`Decimal`), output cap, timeout, retries and the Kestrel URL from environment variables. Missing values fail at startup. |
| `ch03/ticket_prompt.py` | `SYSTEM_PROMPT`, `fetch_ticket()` and `build_user_text()`, shared by every script. |
| `ch03/first_call.py` | One raw SDK call that prints content, stop reason and usage. |
| `ch03/model_client.py` | The provider-neutral interface: `Message`, `Usage`, `ModelResponse`, `ModelError`, the `ModelClient` Protocol, `call_cost_usd()`, `build_client()`. |
| `ch03/anthropic_adapter.py` | `AnthropicAdapter`, the only file that imports the SDK: `complete()`, `stream()`, stop-reason and error mapping. |
| `ch03/fake_model.py` | `FakeModelClient`: scripted replies and errors, every call recorded, `ScriptExhausted` on an extra call. |
| `ch03/draft_reply.py` | The CLI: streams a draft reply to one ticket, then a footer with stop reason, tokens and cost. |
| `tests/test_settings.py` | Defaults, fail-fast validation, the hidden key. |
| `tests/test_draft_reply.py` | The CLI against the fake model, plus one run against the seeded mock API. |
| `tests/test_anthropic_adapter.py` | The real adapter and SDK against a fake HTTP transport (`httpx2.MockTransport`; httpx2 is the HTTP library anthropic 2.8 is built on): stop reasons, usage, errors, retries, streaming. |
| `tests/test_live.py` | Three checks against the real provider (`-m live`, needs a key). |
| `conftest.py` | Puts this folder on `sys.path`; the `kestrel_url` fixture uses your running server, or starts the same seeded API in the test process. |

## Run it

From the book folder (`agentic-ai-foundations/`), once:

```bash
uv sync
```

Then from this folder, in one terminal:

```bash
uv run kestrel up          # writes .kestrel/ and serves http://127.0.0.1:8700; Ctrl+C to stop
```

and in a second terminal:

```bash
uv run pytest
cp .env.example .env       # add your key; check model and prices against your provider's docs
uv run --env-file .env python -m ch03.first_call
uv run --env-file .env python -m ch03.draft_reply T-000407
uv run --env-file .env python -m ch03.draft_reply T-000407 --no-stream
uv run --env-file .env pytest -m live
```

## Expected output

`pytest` reports `28 passed, 3 deselected` (the deselected three are the live tests).

Without a `.env` the CLI stops before any call:

```text
$ uv run python -m ch03.draft_reply T-000407
error: missing or invalid settings: MODEL, INPUT_PRICE_PER_MTOK, OUTPUT_PRICE_PER_MTOK
```

With a key, the draft streams in pieces and ends with one footer line in this format (the
numbers here are the tests' made-up values; yours depend on the ticket, the model and your prices):

```text
stop: finished | in: 1000 | out: 200 | cost: $0.004000
```

Known failures print one line and exit with status 1 (the request id differs on every run):

```text
$ ANTHROPIC_API_KEY=invalid uv run --env-file .env python -m ch03.draft_reply T-000407
error: The API key was rejected. Check ANTHROPIC_API_KEY.
request id: req_011Ch6Rj9MMHUcumxfrMoMM1
$ MODEL_TIMEOUT_S=0.01 uv run --env-file .env python -m ch03.draft_reply T-000407
error: The request timed out (MODEL_TIMEOUT_S=0.01, MAX_RETRIES=2).
```

`MAX_OUTPUT_TOKENS=20` adds `[truncated] This draft hit the output token limit. Do not send it as is.`
above the footer. An unknown ticket (`T-999999`) still ends in an httpx traceback; the chapter's
Exercise 3 fixes that.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
