"""Chapter 13's trace: one JSON object per event of one run, appended and flushed as it happens.

New in Chapter 15: context events (a trim or a compaction), final_check events (each final
answer the loop checked, with its errors), and a run_end written by run_research with the
outcome, the citable set, the search count and the cost.
"""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

from ch15.agent import ContextEvent
from ch15.budget import CallLimits, RunBudget
from ch15.final import FinalCheck
from ch15.model_client import ModelResponse, ToolCall, ToolResult
from ch15.pricing import Price, cost_of


class TraceRecorder:
    """Writes one JSON object per event to a new .jsonl file. Use it in a with block."""

    def __init__(self, path: Path, price: Price | None) -> None:
        self.path = path
        self._price = price
        self._file: TextIO | None = None
        self.model_usd: Decimal | None = Decimal(0) if price else None  # None: unpriced

    def __enter__(self) -> "TraceRecorder":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("x", encoding="utf-8")  # an existing file is an error
        return self

    def __exit__(self, *exc: object) -> None:
        if self._file is not None:
            self._file.close()

    def _write(self, kind: str, **fields: Any) -> None:
        if self._file is None:
            raise RuntimeError("TraceRecorder must be used in a with block")
        record = {"kind": kind, "ts": datetime.now(UTC).isoformat(), **fields}
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()  # every event leaves the process before the loop moves on

    def run_start(
        self, run_id: str, question: str, today: str, model: str, budget: RunBudget, prompt: str
    ) -> None:
        self._write(
            "run_start",
            run_id=run_id,
            question=question,
            today=today,
            prompt=prompt,  # e.g. research_assistant_v1
            model=model,  # the configuration's name, never a key
            price_as_of=self._price.as_of if self._price else None,
            budget=asdict(budget),
        )

    def model_call(
        self, step: int, response: ModelResponse, limits: CallLimits, duration_ms: int
    ) -> None:
        usage = response.usage
        cost = (
            cost_of(usage.input_tokens, usage.output_tokens, self._price) if self._price else None
        )
        if cost is not None and self.model_usd is not None:
            self.model_usd += cost
        self._write(
            "model_call",
            step=step,
            stop_reason=response.stop_reason,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=None if cost is None else float(cost),
            max_output_tokens=limits.max_output_tokens,
            duration_ms=duration_ms,
            text=response.text,
            tool_calls=[c.name for c in response.tool_calls],
        )

    def tool_call(self, step: int, call: ToolCall, result: ToolResult, duration_ms: int) -> None:
        self._write(
            "tool_call",
            step=step,
            call_id=call.id,
            tool=call.name,
            args=call.arguments,
            is_error=result.is_error,
            content=result.content,  # the whole result, exactly as the model saw it
            duration_ms=duration_ms,
        )

    def context(self, step: int, event: ContextEvent) -> None:
        self._write("context", step=step, **event.model_dump(mode="json"))

    def final_check(self, step: int, check: FinalCheck) -> None:
        self._write("final_check", step=step, accepted=check.accepted, errors=check.errors)

    def run_end(self, **fields: Any) -> None:
        self._write("run_end", **fields)


def read_trace(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]
