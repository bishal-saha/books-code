# Agentic AI Foundations: companion code

> Code for the free book **[Agentic AI Foundations: From LLM Calls to Your First Agent](https://iambishal.com/resources/books/agentic-ai-foundations)**, book 1 of the *Agentic AI* series on iambishal.com.
> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Python | 3.12 (`uv` reads `.python-version`) |
| Packages | anthropic 2.8, pydantic 2.14, httpx 0.28, and the shared [`kestrel-outfitters`](../_shared/kestrel) package |
| Tests | `uv run pytest` (no API key, no network: fake model and a local mock API) |
| Live examples | copy `.env.example` to `.env`, then `uv run pytest -m live` in a chapter folder |

## Set up

```bash
uv sync
uv run kestrel up          # writes .kestrel/ and starts the mock API on http://127.0.0.1:8700
```

Each chapter folder stands alone: `chNN-<slug>/` holds the package `chNN/`, its tests and a README with the commands and expected output.

## Chapters

| # | Chapter | Folder |
|---|---|---|
| 1 | What "agentic" really means: workflows vs agents and the autonomy spectrum | _in progress_ |
| 2 | How LLMs work, just enough: tokens, context windows, sampling and reasoning models | _in progress_ |
| 3 | Talking to models: APIs, messages, system prompts and streaming | _in progress_ |
| 4 | Prompting for agents: instructions, examples, roles and prompt structure | _in progress_ |
| 5 | Structured outputs: JSON Schema, validation and recovering from bad output | _in progress_ |
| 6 | Tool calling from first principles: schemas, the call/result cycle and parallel calls | _in progress_ |
| 7 | The agent loop: perceive, reason, act, observe, stop | _in progress_ |
| 8 | Designing good tools: naming, descriptions, errors, idempotency and granularity | _in progress_ |
| 9 | Context engineering basics: what goes in the window and why it matters | _in progress_ |
| 10 | Short-term memory: conversation state, summarisation and compaction | _in progress_ |
| 11 | Choosing a model: capability, latency, cost, open vs hosted | _in progress_ |
| 12 | Agent frameworks landscape: when to use one, when to write the loop yourself | _in progress_ |
| 13 | Testing your first agent: golden tasks, traces and simple evals | _in progress_ |
| 14 | Capstone I, Design: Kestrel's research assistant (spec, tools, loop) | _in progress_ |
| 15 | Capstone II, Build: the agent end to end, with web search, files and citations | _in progress_ |
| 16 | Capstone III, Harden: error handling, cost limits and a small eval suite | _in progress_ |

The capstone (chapters 14–16) lives in `capstone/`: `starter/`, then the project at the end of each capstone chapter.

## Licence

MIT, see [LICENSE](../../LICENSE).
