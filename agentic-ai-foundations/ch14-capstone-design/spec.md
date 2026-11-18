# Research assistant: design spec (v1)

Kestrel Outfitters is a fictional company; any resemblance to real businesses or products is coincidental.

## Problem
Sam Adeyemi (CTO) wants answers to engineering and business questions from the public web
and from local Kestrel exports, with every claim checkable by the reader.

## Users
Kestrel staff asking one question at a time from a terminal.

## Requirements
| ID | Requirement | Verified by |
|----|-------------|-------------|
| R1 | Every entry in `claims` cites a URL or sandbox-relative file path a tool returned in this run. | FinalAnswer validators + check_citations, every run |
| R2 | When the tools don't cover the question, the status is `needs_info`, never a guess. | Golden tasks quarter-not-covered and sandbox-probe |
| R3 | A hard run budget per question: steps, tokens, wall time and money, enforced by the loop. | Fake-model runs that force a limit and check its StopCause (Chapters 15-16; money's cost_limit from Chapter 16) |
| R4 | Works with any provider whose model supports tool calling, behind the model client. | Tests on the fake model; the reader runs the golden tasks through Chapter 11's two adapters with their own keys |
| R5 | Runs from the command line: the question as an argument, an optional `--today`. | CLI smoke test |

## Non-goals
- No retrieval or vector index (Book 2), no MCP (Book 3), no named patterns beyond the
  agent loop (Book 4), no multi-agent setup (Book 5), no deployment or observability
  platform (Books 6-8).
- No write actions. Adding one reopens the autonomy placement.
- Nothing carries over between questions: each question is a fresh run.

## Autonomy placement
- Point 5: an agent with a wider tool set, because search_web reaches the open web, an
  open-ended source.
- Reach: read-only. search_web (public web), read_file and count_rows (.kestrel/exports
  only), calculate (no I/O). Read-only keeps the risk low; it doesn't make this point 4.
- Not point 3: question shapes vary, so code can't fix the steps in advance.
- Not point 4: without search_web, the public half of the question goes unanswered.
- Adding any write tool reopens the placement and needs a separate design.

## Definitions
- A shipment is late when `late` is `yes` in shipments.csv; it belongs to the period that
  contains its `shipped_at` date.
- "Last quarter" is the last full calendar quarter before the run's date (`--today`).
- URL match: lowercase scheme and host, drop the fragment, keep everything else.

## Tools (contracts in ch14/tools.py)
search_web, read_file, count_rows, calculate. count_rows is a fourth tool beyond the
outline's three: one quarter of shipments is 106 read_file pages at the 6,000-character
maximum (design_check).

## Budget (defaults in ch14/settings.py)
8 steps, 60,000 tokens, 120 s wall time, USD 0.50 (enforced from Chapter 16),
10 s per search call.

## Build or adopt (from ch12-agent-frameworks/decisions/capstone.md)
- Build: Chapter 7's run_agent, no agent framework.
- Why: Chapter 12's checklist question on need finds none (one question per run,
  short-term state, no approval step, no fixed sequence); the teaching goal; Chapters 3
  and 11's adapters cover portability.
- Revisit if runs must survive a restart, a human approval step is added, or the work
  splits across several agents.
- Model: a hosted configuration, on the assumption that tool results hold read-only
  synthetic data. Real finance or customer data in tool results reopens Chapter 11's
  data-handling gate. Chapter 16 re-runs the comparison on the golden tasks before the
  final model choice.

## Known limitations
- Single agent with short-term memory only: conversation state lasts one run.
- Web evidence is titles and snippets only (no page fetch). A fetch tool would mean larger
  results, more cost and more untrusted text in the window; adding one is a spec change
  with its own cap and security row.
- Kestrel's carriers are fictional: live search is unlikely to find them, and may return
  pages about unrelated firms. Carrier golden tasks use hand-written search fixtures.
- Live web results change, so live answers aren't reproducible.
- Confidence is the model's own label, not a calibrated probability.
- Citation checking proves a location was retrieved, not that it supports the claim.
- A period the export covers only in part gives a count that is too low; the refusal rule
  catches only a period with no rows at all.
- Code checks claims and citations, not the `answer` summary.
- A budget stops new calls; the last call can overshoot the token (later money) budget by
  at most that one call.
- The file sandbox is a path check, not process isolation.

## Open questions (Chapter 15)
- How a search service plugs in behind SearchBackend (the book names none).
- What the loop returns when a final message still fails validation after its one retry.
- How the command line prints each outcome (answer, needs_info, budget stop), and its exit codes.

## Security model
| Control | Enforced in | Prevents | Doesn't prevent |
|---|---|---|---|
| File sandbox | resolve_in_sandbox, before opening | Reading outside .kestrel/exports | Files changed by another process; untrusted contents |
| Input validation | Registry, strict pydantic models | Malformed or unknown arguments | Well-formed arguments chosen for bad reasons |
| No shell or code execution | Tool set; calculate's grammar | An expression that runs code | Correct arithmetic on wrong numbers |
| Read-only tools | Tool contracts | Any change to any system | Wrong answers; export rows leaking into search queries |
| Keys from the environment, sent in headers | Settings, HTTP clients | Keys in prompts, the repo or URLs | A key typed into a question |
| Tool errors written by our code | Each tool, registry | Exception text reaching the model | A secret inside normal output |
| `<data>` delimiters, tag characters escaped | render_tool_result | Tool text blurring into our instructions (clarity, not a security boundary) | Prompt injection |
| TOOL_RESULT_MAX_CHARS | Registry | One result flooding the context window | Many results within the budget |
| Provider and search service chosen on data handling (Chapter 11) | Settings | Sending data to a service whose terms don't allow it | Questions and export rows leaving the machine |
