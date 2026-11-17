# Known limitations of the research assistant (Chapter 16)

What the assistant does not do, as of the end of *Agentic AI Foundations*. Lines marked
"Next" point to a later book in the series.

- One agent loop, one model, four read-only tools (search_web, read_file, count_rows,
  calculate). No design patterns beyond the agent loop. Next: Book 4.
- One agent: no hand-offs between agents. Next: Book 5.
- No retrieval over Kestrel's internal documents and no state between questions: every run
  starts with an empty conversation. Next: Book 2.
- The tools are local Python functions. No other program can call them; they are not exposed
  over MCP. Next: Book 3.
- The file sandbox is a path check, not process isolation. Delimiting tool results reduces the
  risk from instructions hidden in web snippets; it does not remove it. Next: Books 6 to 8.
- No deployment, monitoring or fail-over: the SDK's retries leave no record in the trace, and
  there is no second model to fall back to. Next: Books 6 to 8.
- The assistant can cite only what search_web returned. For carriers the web says nothing
  about, the answer lists the web half under `missing`.
- The search backend is illustrative: adapt HttpSearchBackend to your service's API before
  trusting its error handling.
- Prices are configuration and they drift. Recheck `[config.price]` in models.toml and
  SEARCH_USD_PER_QUERY before trusting a cost or a money budget.
- The money check before each call uses an estimate of the input, so the last call can go over
  the money budget by at most that one call. Every search request is charged when sent, which
  may overstate what a provider bills for a failed request.
- A model call that fails returns no usage, so it is not charged, although a provider may still
  bill for it. A 429 is classified as transient; a provider's spend-cap 429 is really permanent,
  so check your provider's error reference and map it in the adapter if it can be told apart.
- A stopped run prints what the tools returned, unchecked, and no answer. It never asks the
  model for a summary after a limit is hit.
- The offline eval runs fake-model scripts: it tests the harness, the checks and the failure
  handling, not a model. Only a live eval (`python -m ch16.eval --live`) measures a model, and
  six golden tasks are a small sample.
