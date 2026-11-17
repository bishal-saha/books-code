# Build-or-adopt checklist

## 0. Placement (autonomy spectrum)
- Single model call, or a workflow with no durable needs: stop. No framework.
- Workflow that needs approval steps, pause/resume or persistence: go to 1.
  A graph library here is a workflow tool; there is no agent loop to replace.
- Agent: go to 1.

## 1. Need (now, not someday)
- Persistence: must run state survive a process restart?
- Hooks: must our code run at fixed points of the loop?
- Graph orchestration: fixed steps, approvals, pause/resume?

## 2. Visibility (hard gate)
- Can we see every prompt and response sent to the model?
- Can we run the unit tests with a fake model and no API key?

## 3. Limits (hard gate)
- Is the run budget checked before each model call?
- At the limit: exception, or a partial result with a stop cause and the step log?

## 4. Errors (hard gate)
- Unknown tool: tool result or exception?
- Tool failure: tool result or exception?

## 5. Reach (hard gate)
- Which built-in tools does it bring, and can we turn each one off?

## 6. Portability (weighed)
- Does it work with every provider our adapters support?

## 7. Churn (weighed)
- Beta, dated beta names or 0.x versions on the parts we would use?
- How many of our modules would import its types (exit cost)?

Pass rule for gates 3 and 4: our callers check StopCause, so a default that
raises passes only if a documented setting returns a tool result or a partial
result instead, and a fake-model test proves it. Raising is a valid design in
general; these gates test fit to our callers.

Gates not yet answered by the docs: spike first (fake-model tests against the
candidate), then adopt or build.
Partial adoption counts: a framework can own one capability (an approval pause,
checkpoints) while our loop stays the agent step.
