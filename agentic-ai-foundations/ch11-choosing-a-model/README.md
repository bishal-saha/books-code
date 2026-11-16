# Chapter 11: Choosing a model

> Code for **[Choosing a model: capability, latency, cost, open vs hosted](https://iambishal.com/resources/books/agentic-ai-foundations/read/choosing-a-model)**, chapter 11 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch11.compare_models --fake` (no key) |
| Tests | `uv run pytest` (no key, no network: fake model, `httpx.MockTransport`, and the mock API started in-process if it is not running) |
| Keys | copy `.env.example` to `.env` and `models.example.toml` to `models.toml` for runs with real endpoints |

## Run it

```bash
cd books-code/agentic-ai-foundations/ch11-choosing-a-model
uv run kestrel up                                # terminal 1: http://127.0.0.1:8700
uv run python -m ch11.compare_models --fake      # terminal 2: scripted fake-model configurations
uv run pytest                                    # 47 tests
```

Expected output of the `--fake` run (fake-model output: scripted answers, invented token counts,
illustrative prices; only the tool results come from the mock API):

```text
[fake model: scripted replies and token counts; tool results from Kestrel]
fake-correct
  success 18/18   finished 18   model_error 0   invalid args 0
  per task  order-status 3/3  order-carrier 3/3  most-stock 3/3  ticket-triage 3/3  outdated-policy 3/3  shipment-plus-policy 3/3
  wall s    - (fake model: timing means nothing)
  tokens    mean 3140 per run
  cost      total 0.0666 USD   per success 0.0037 USD
fake-wrong-tool
  success 0/18   finished 18   model_error 0   invalid args 0
  per task  order-status 0/3  order-carrier 0/3  most-stock 0/3  ticket-triage 0/3  outdated-policy 0/3  shipment-plus-policy 0/3
  wall s    - (fake model: timing means nothing)
  tokens    mean 3140 per run
  cost      total 0.0666 USD   per success n/a
  failures  no required tool call
local-server
  skipped: not configured (LOCAL_COMPAT_MODEL, LOCAL_COMPAT_API_KEY, LOCAL_COMPAT_BASE_URL empty)
36 rows written to results/results.csv (expected 36)
```

With real endpoints: fill in `.env` and the prices in `models.toml`, then
`uv run python -m ch11.compare_models`. Candidates with empty variables are skipped as
"not configured"; a candidate whose preflight call is rejected (wrong model name, an effort
value the model doesn't accept, a bad key) is skipped with the reason.

## What's here

The folder stands alone: files marked "copied" come from Chapter 9's folder, with the change noted.

| File | What it shows |
|---|---|
| `ch11/openai_compatible_adapter.py` | New. The second ModelClient adapter: chat completions over httpx, mapped onto Chapter 7's shapes. |
| `ch11/configs.py` | New. `ModelConfig`, `Price`, `load_configs`, `make_client`, `ConfigError`. |
| `ch11/pricing.py` | New. `cost_of`, `run_cost`, `next_call_ceiling` (Decimal; unpriced is `None`, never zero). |
| `ch11/kestrel_tools.py` | New. The read-only comparison tool set: Chapter 9's three tools plus `get_stock`, `get_ticket`, `list_policies`, `get_policy`. |
| `ch11/tasks.py` | New. The six Kestrel tasks, their answer models, expected values read from the API, and `failure_label`. |
| `ch11/compare_models.py` | New. The harness: preflight, runs, `results/results.csv`, `results/summary.txt`. |
| `ch11/scripted.py` | New. The scripted fake-model configurations for `--fake` and the tests. |
| `ch11/prompts/compare_v1.md` | New. The comparison prompt, in Chapter 4's six sections. |
| `models.example.toml` | New. Three candidate configurations; prices are `SET-ME` until you fill them in. |
| `tests/fixtures/*.json` | New. Hand-written chat completions responses (not recorded from any server). |
| `ch11/tools.py` | Copied. Argument models now forbid unknown fields (`StrictArgs`). |
| `ch11/settings.py` | Copied. `MODEL` is optional and the price pair is gone (prices live in `models.toml`); adds `COMPARE_RUNS`. |
| `ch11/anthropic_adapter.py` | Copied. Raises a clear error if the model or key is missing. |
| `ch11/model_client.py`, `fake_model.py`, `agent.py`, `budget.py`, `inspector.py`, `context_budget.py`, `results.py`, `truncate.py`, `prompts.py` | Copied unchanged. |
