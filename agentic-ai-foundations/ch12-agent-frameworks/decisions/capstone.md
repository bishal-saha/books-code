# Decision: research assistant agent loop

Decision: hand-written agent loop (run_agent), no agent framework.
Placement: agent with narrow tools and a tight budget; read-only reach.
Context: one question per run from the command line; four read-only tools
(search_web, read_file from the sandboxed folder, count_rows, calculate);
no shell;
run budget per question of steps, tokens and wall time, plus money (designed
in Chapter 14, enforced in Chapter 16); any provider whose model supports
tool calling.
Need: none (checklist Q1). No persistence, hook or graph need; one run,
short-term state only. No need means build.
Gates: not run against a named candidate; our loop meets them (late-shipments).
Separate reason: teaching goal; every line of the loop is readable and explained.
Portability: required; met by the Chapter 3 and Chapter 11 adapters. The
Anthropic tool runner ships inside Anthropic's SDK and the Agent SDK runs the
bundled Claude Code CLI; other providers were not checked for either.
Accepted costs: we maintain the loop; no built-in sessions or tracing UI.
We build these: retries and failure classes, and the money limit with its
cost_limit stop cause (Chapter 16).
Revisit if: runs must survive a process restart; a human approval step is
added; the work splits across several agents (Book 5).
