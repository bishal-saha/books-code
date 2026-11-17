# Decision: expense-claim extraction

Decision: no framework; no agent loop.
Placement: workflow with model steps (code fixes the sequence).
Need: none. Nothing waits for approval or has to survive a restart.
Gates: not reached; the checklist stops at question 0.
Revisit if: the model must choose which records to fetch
(for example, looking up past claims on its own).
