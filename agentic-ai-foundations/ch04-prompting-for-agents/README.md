# Chapter 4: Prompting for agents

> Code for **[Prompting for agents: instructions, examples, roles and prompt structure](https://iambishal.com/resources/books/agentic-ai-foundations/read/prompting-for-agents)**, chapter 4 of *Agentic AI Foundations* on iambishal.com.
> Read the chapter first; this folder is its runnable companion.

> Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

| | |
|---|---|
| Type | Book chapter |
| Tested with | Python 3.12 · anthropic 2.8 · pydantic 2.14 · httpx 0.28 · kestrel-outfitters 0.3.0 · last verified 2026-11-18 |
| Run | `uv run --env-file .env python -m ch04.compare support_reply 1 2` |
| Tests | `uv run pytest` (fake model, no key) |
| Keys | `ANTHROPIC_API_KEY` and `MODEL` for `compare` only (see `.env.example`; `MODEL_THINKING=off` by default) |

## What's here

| File | What it shows |
|---|---|
| `ch04/prompts/support_reply_v1.md` | Chapter 3's system prompt, as version 1 of a prompt file. |
| `ch04/prompts/support_reply_v2.md` | The structured prompt: role, task, constraints, data, output format, the don't-know rule and two few-shot examples. |
| `ch04/prompt_builder.py` | Loads a prompt file, renders a ticket and its records as delimited data, sends one request. |
| `ch04/compare.py` | Runs two prompt versions on the same tickets and prints a Markdown report. |
| `ch04/demo_drafts.py` | Scripted, illustrative drafts for `compare --fake` (no key, not real model output). |
| `ch04/show_request.py` | Prints the user message for one ticket (no model call). |
| `ch04/tickets.json` | The five seeded tickets the comparison uses. |
| `ch04/fixtures/embedded_instruction.json` | A local ticket whose text tries to close its own tag and give orders. |
| `ch04/model_client.py`, `anthropic_adapter.py`, `fake_model.py`, `settings.py` | Chapter 3's model client, trimmed to `complete()`. |
| `tests/` | Structure tests, the fake-model request test, the adapter's request (thinking off), a full comparison run on the seeded API, and one `live` test. |

## Run it

From the book folder (`agentic-ai-foundations/`), once: `uv sync`. Then from this folder, in one terminal:

```bash
uv run kestrel up          # serves http://127.0.0.1:8700; Ctrl+C to stop
```

and in a second terminal:

```bash
uv run pytest
uv run python -m ch04.show_request T-000007
uv run python -m ch04.compare support_reply 1 2 --fake --extra ch04/fixtures/embedded_instruction.json
cp .env.example .env       # add your key and a current model from your provider
uv run --env-file .env python -m ch04.compare support_reply 1 2 --extra ch04/fixtures/embedded_instruction.json > report.md
```

## Expected output

`pytest` reports `20 passed, 1 deselected` (the live test). `show_request T-000007` prints:

```text
<ticket>
<ticket_id>T-000007</ticket_id>
<channel>web form</channel>
<order_id>none</order_id>
<subject>Where is my order?</subject>
<messages>
<message from="customer" sent_at="2025-08-10">Where is my order?.</message>
</messages>
</ticket>
<data>
<order>none</order>
<shipment>none</shipment>
<policies>{"returns-policy": "# Returns policy ... (both current policies, as JSON)</policies>
</data>
```

`compare --fake` (scripted demo drafts, labelled as fake-model output) starts its report with:

```markdown
# support_reply v1 vs v2

Model: fake (scripted demo drafts) · max output tokens: 400 · tickets: 6

| Ticket | Probe | v1 | v2 |
|---|---|---|---|
| T-000407 | late delivery | 20 words · no flags | 42 words · no flags |
| T-000554 | return request | 21 words · no flags | 38 words · no flags |
| T-001398 | trade pricing | 25 words · no flags | 23 words · NEEDS INFO |
| T-000007 | missing order | 16 words · no flags | 34 words · NEEDS INFO |
| T-000145 | damaged item | 14 words · no flags | 39 words · no flags |
| T-LOCAL-1 | local fixture | 25 words · no flags | 36 words · no flags |
```

With a key, `compare` makes twelve model calls (six tickets, two versions) and writes a summary table followed by every draft. The drafts come from a real model, so they differ from run to run; run it more than once before you trust a difference.

## Licence

MIT, see the repository's [LICENSE](../../LICENSE).
