"""Golden tasks: the file format, its validation, and the answer shapes tasks can require."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GOLDEN_TASKS = Path(__file__).resolve().parent.parent / "golden_tasks.toml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a misspelt field is an error, not ignored


class ToolExpectation(Strict):
    tool: str
    args: dict[str, object] = {}  # a subset: other arguments are allowed


class FactExpectation(Strict):
    value: str | int | bool
    field: str | None = None  # check one field of the parsed output, not the raw text

    @model_validator(mode="after")
    def raw_text_facts_are_strings(self) -> "FactExpectation":
        if self.field is None and not isinstance(self.value, str):
            raise ValueError("a fact without a field is a substring, so its value must be text")
        return self


# --- Answer shapes a task can require (Chapter 5: validate, never trust) ---


class OrderStatus(Strict):
    order_id: str
    status: str


class ShipmentCheck(Strict):
    order_id: str
    carrier: str
    late: bool


class StockTotal(Strict):
    sku: str
    total_on_hand: int = Field(ge=0)


class TicketLink(Strict):
    ticket_id: str
    order_id: str
    priority: str


SCHEMAS: dict[str, type[BaseModel]] = {
    m.__name__: m for m in (OrderStatus, ShipmentCheck, StockTotal, TicketLink)
}


class GoldenTask(Strict):
    id: str
    input: str
    required_tool_calls: list[ToolExpectation] = []
    required_any_tool: list[str] = []
    forbidden_tool_calls: list[ToolExpectation] = []
    required_facts: list[FactExpectation] = []
    output_schema: str | None = None
    max_steps: int = Field(gt=0)

    @field_validator("output_schema")
    @classmethod
    def schema_is_known(cls, name: str | None) -> str | None:
        if name is not None and name not in SCHEMAS:
            raise ValueError(f"unknown output schema {name!r}")
        return name

    @model_validator(mode="after")
    def fields_need_a_schema(self) -> "GoldenTask":
        if self.output_schema is None and any(f.field for f in self.required_facts):
            raise ValueError("a fact with a field needs an output_schema to parse it")
        return self


def load_golden_tasks(path: Path = GOLDEN_TASKS) -> list[GoldenTask]:
    with path.open("rb") as f:
        tasks = [GoldenTask(**entry) for entry in tomllib.load(f)["task"]]
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("golden task ids must be unique")
    return tasks


def check_tool_names(tasks: list[GoldenTask], known: set[str]) -> None:
    """Run before any trial: a task naming a missing tool would fail every trial."""
    for task in tasks:
        named = [e.tool for e in task.required_tool_calls + task.forbidden_tool_calls]
        for tool in named + task.required_any_tool:
            if tool not in known:
                raise ValueError(f"{task.id}: no tool named {tool!r} in the registry")
