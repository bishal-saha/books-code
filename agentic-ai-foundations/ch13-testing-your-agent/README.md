# Chapter 13: Testing your first agent

> Code for **[Testing your first agent: golden tasks, traces and simple evals](https://iambishal.com/resources/books/agentic-ai-foundations/read/testing-your-agent)**, chapter 13 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-17 |
| Run | `uv run python -m ch13.eval` (fake model, no key) |
| Tests | `uv run pytest` (no key: fake model, `httpx.MockTransport`, and the mock API started in-process if it is not running) |
| Keys | only `--live` needs one: copy `.env.example` to `.env` and `models.example.toml` to `models.toml` |

## Run it

```bash
cd books-code/agentic-ai-foundations/ch13-testing-your-agent
uv run kestrel up                          # terminal 1: http://127.0.0.1:8700
uv run pytest                              # terminal 2: 28 tests
uv run python -m ch13.eval                 # 6 golden tasks x 5 trials on the fake model
```

Expected output of the eval (fake-model output: scripted replies and token counts, an
illustrative price; only the tool results come from the mock API):

```text
[fake model: scripted replies and token counts; tool results from Kestrel]
task                         pass   pass@k  pass^k  avg cost  avg steps  stop causes              top failure
order-status                 5/5    yes     yes     $0.0028   2.0        finished=5               -
shipment-late                5/5    yes     yes     $0.0028   2.0        finished=5               -
stock-total                  4/5    yes     no      $0.0032   2.4        finished=4 step_limit=1  stopped by step_limit
ticket-order                 5/5    yes     yes     $0.0028   2.0        finished=5               -
unknown-order-needs-info     5/5    yes     yes     $0.0028   2.0        finished=5               -
late-top-carrier-needs-info  3/5    yes     no      $0.0028   2.0        finished=5               missing fact: NEEDS INFO
overall                      27/30  6/6     4/6     spent $0.0846 of $0.50 cap, 0 skipped
```

Each trial's trace lands in `traces/<eval_id>/<task_id>-t<trial>.jsonl` (git-ignored: traces hold
real tool arguments and results). With a real model: fill in `.env` and a priced configuration in
`models.toml`, then `uv run python -m ch13.eval --live --config hosted-sdk`. It refuses to start
without a price, because the eval's cost cap is in money.

`uv run python -m ch13.sample_traces` regenerates the two sample traces in `fixtures/traces/`.

## What's here

The folder stands alone: files marked "copied" come from Chapter 11's folder, with the change noted.

| File | What it shows |
|---|---|
| `ch13/trace.py` | New. `TraceRecorder` (one flushed JSONL line per event, mode `"x"`) and `read_trace`. |
| `ch13/golden.py` | New. The golden-task format (`GoldenTask`), answer shapes, `load_golden_tasks`, `check_tool_names`. |
| `ch13/grading.py` | New. Deterministic graders: `Check`, `grade` and one check per expectation. |
| `ch13/eval.py` | New. `run_eval` (trial-major, cost cap, one trace per trial), `summarise`, `format_report`, the CLI. |
| `ch13/scripted.py` | New. Test helpers (`tool_use`, `finished`, `never_stops`, `FakeClock`) and the fake-model scripts. |
| `ch13/sample_traces.py` | New. Regenerates `fixtures/traces/wrong_carrier.jsonl` and `wrong_stock.jsonl`. |
| `ch13/prompts/operations_v1.md` | New. The operations agent's prompt, in Chapter 4's six sections. |
| `golden_tasks.toml` | New. Six golden tasks; facts checked against the seeded API by `tests/test_golden.py`. |
| `ch13/agent.py` | Copied. `run_agent` gains one optional `recorder` parameter; Chapter 9's inspector is left out. |
| `ch13/kestrel_tools.py` | Copied. `build_ops_registry`: the read tools without the policy pair. |
| `ch13/settings.py` | Copied. Adds `PROMPT_VERSION`, `EVAL_TRIALS`, `EVAL_MAX_COST_USD`; drops `COMPARE_RUNS`. |
| `ch13/pricing.py` | Copied. `cost_of` only. |
| `ch13/model_client.py`, `fake_model.py`, `budget.py`, `tools.py`, `results.py`, `truncate.py`, `prompts.py`, `configs.py`, `anthropic_adapter.py`, `openai_compatible_adapter.py` | Copied unchanged. |
