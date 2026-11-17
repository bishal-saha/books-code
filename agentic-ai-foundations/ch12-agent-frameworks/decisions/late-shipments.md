# Decision: late-shipment investigation

Decision: build (keep run_agent).
Placement: agent with narrow tools and a tight budget; read-only reach.
Need: none now. One command-line run, short-term state only.
Gates: met by our loop (Chapter 11's version) and shown by fake-model tests:
budget checked before each call, partial result with a StopCause at a limit,
invented arguments, unknown tools and tool failures returned as error results
(tests/test_edges.py).
Revisit if: runs must survive a process restart, or the tool set gains a write.
