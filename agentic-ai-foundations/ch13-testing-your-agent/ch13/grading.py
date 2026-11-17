"""Deterministic graders: each expectation becomes a check with a reason. No model is called."""

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from ch13.golden import SCHEMAS, GoldenTask, ToolExpectation


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    reason: str = ""  # empty on a pass, so the report only shows failures


def check_stop(run_end: dict) -> Check:
    cause = run_end["stop_cause"]
    return Check("stop", cause == "finished", "" if cause == "finished" else f"stopped by {cause}")


def check_tool_calls(task: GoldenTask, events: list[dict]) -> list[Check]:
    calls = [e for e in events if e["kind"] == "tool_call"]

    def seen(exp: ToolExpectation) -> bool:  # name plus a subset of arguments, in any order
        return any(
            c["tool"] == exp.tool and all(c["args"].get(k) == v for k, v in exp.args.items())
            for c in calls
        )

    checks = []
    for exp in task.required_tool_calls:
        ok = seen(exp)
        checks.append(Check("tool_calls", ok, "" if ok else f"missing call: {exp.tool} {exp.args}"))
    if task.required_any_tool:
        ok = any(c["tool"] in task.required_any_tool for c in calls)
        reason = "" if ok else f"no call to any of {task.required_any_tool}"
        checks.append(Check("tool_calls", ok, reason))
    for exp in task.forbidden_tool_calls:
        ok = not seen(exp)
        checks.append(Check("tool_calls", ok, "" if ok else f"forbidden call: {exp.tool}"))
    return checks


def check_schema(task: GoldenTask, output: str) -> tuple[BaseModel | None, list[Check]]:
    if task.output_schema is None:
        return None, []
    try:  # strict on purpose: a code fence or a friendly sentence around the JSON fails
        parsed = SCHEMAS[task.output_schema].model_validate_json(output)
    except ValidationError as exc:
        return None, [Check("schema", False, f"{task.output_schema}: {exc.error_count()} error(s)")]
    return parsed, [Check("schema", True)]


def check_facts(task: GoldenTask, output: str, parsed: BaseModel | None) -> list[Check]:
    checks = []
    for fact in task.required_facts:
        if fact.field is None:
            ok = isinstance(fact.value, str) and fact.value in output
            label = str(fact.value)
        else:
            ok = parsed is not None and getattr(parsed, fact.field, None) == fact.value
            label = f"{fact.field}={fact.value}"
        checks.append(Check("facts", ok, "" if ok else f"missing fact: {label}"))
    return checks


def grade(task: GoldenTask, events: list[dict]) -> list[Check]:
    """A trial passes only when every check passes."""
    run_end = next((e for e in reversed(events) if e["kind"] == "run_end"), None)
    if run_end is None:
        return [Check("stop", False, "no run_end: the run did not complete")]
    stop = check_stop(run_end)
    if not stop.passed:
        return [stop]  # a partial result has no answer to grade
    output = run_end["output"]
    parsed, schema_checks = check_schema(task, output)
    return [
        stop,
        *check_tool_calls(task, events),
        *schema_checks,
        *check_facts(task, output, parsed),
    ]
