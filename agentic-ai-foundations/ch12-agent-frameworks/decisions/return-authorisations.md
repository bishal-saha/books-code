# Decision: return authorisations with human approval

Decision: spike, then adopt LangGraph if it passes gates 2 to 5; else build.
Placement: agent with a wider tool set: the model picks the lookups and whether
to propose a return; code fixes one edge, approval before the write
(create_return_authorisation, local SQLite store, Chapter 8).
Need: persistence across restarts and an approval pause. Its docs cover both:
a checkpoint per super-step, keyed by thread_id, used for human-in-the-loop
resume. The in-memory savers lose everything on restart, so production needs
a persistent one.
Gates: to test in the spike, with fake-model tests: visibility of prompts,
limits (stop cause or exception?), unknown-tool handling, built-in tools.
Portability and churn: weighed after the spike.
Build cost if we fall back: versioned JSON state per step, a pending_approvals
table, a dispatcher check, a new stop cause for "awaiting approval", a resume
path that reuses the idempotency key, and answers for crashes between approval
and execution, racing resumes, stale approvals and who may approve. Stored
state holds customer data.
Revisit if: the spike fails a gate, or approval moves out of the agent.
