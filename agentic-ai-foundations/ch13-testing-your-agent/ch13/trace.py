"""The trace: one JSON object per event of one run, appended and flushed as it happens."""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

from ch13.agent import RunResult
from ch13.budget import CallLimits, RunBudget
from ch13.configs import Price
from ch13.model_client import ModelResponse, ToolCall, ToolResult
from ch13.pricing import cost_of


class TraceRecorder:
    """Writes one JSON object per event to a new .jsonl file. Use it in a with block."""

    def __init__(self, path: Path, price: Price | None) -> None:
        self.path = path
        self._price = price
        self._file: TextIO | None = None
        self.cost_usd: Decimal | None = Decimal(0) if price else None  # None: unpriced

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
        self, run_id: str, task_id: str | None, prompt: str, model: str, budget: RunBudget
    ) -> None:
        self._write(
            "run_start",
            run_id=run_id,
            task_id=task_id,
            prompt=prompt,  # e.g. operations_v1
            model=model,  # the configuration's name, never a key
            sampling="provider default",  # our ModelClient sends no temperature
            price_as_of=self._price.as_of if self._price else None,
            budget=asdict(budget),
        )

    def model_call(
        self, step: int, response: ModelResponse, limits: CallLimits, duration_ms: int
    ) -> None:
        cost = cost_of(response.usage, self._price)
        if cost is not None and self.cost_usd is not None:
            self.cost_usd += cost
        self._write(
            "model_call",
            step=step,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=None if cost is None else float(cost),
            max_output_tokens=limits.max_output_tokens,
            duration_ms=duration_ms,
            text=response.text,  # empty when the model only asked for tools
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

    def run_end(self, result: RunResult) -> None:
        self._write(
            "run_end",
            stop_cause=result.cause.value,
            steps=len(result.steps),
            total_tokens=result.total_tokens,
            cost_usd=None if self.cost_usd is None else float(self.cost_usd),
            output=result.final_text,
        )


def read_trace(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]
