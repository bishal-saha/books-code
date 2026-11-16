"""Reasoning tokens are billed as output: two effects, shown with the fake model."""

from datetime import date
from decimal import Decimal

from ch11.agent import run_agent
from ch11.budget import CallLimits, RunBudget, StopCause
from ch11.configs import Price
from ch11.fake_model import FakeModelClient
from ch11.model_client import ModelResponse, Usage
from ch11.pricing import run_cost
from ch11.tools import ToolRegistry

PRICE = Price(input_per_mtok=Decimal("1"), output_per_mtok=Decimal("5"),
              as_of=date(2026, 11, 16), source_url="illustrative")  # fmt: skip
BUDGET = RunBudget(max_steps=4, max_total_tokens=50_000, max_wall_seconds=60.0)
LIMITS = CallLimits(max_output_tokens=4_000, timeout_seconds=30.0)
ANSWER = '{"standard_delivery_working_days": 3}'


def answered(output_tokens: int, stop: str = "finished", text: str = ANSWER) -> FakeModelClient:
    usage = Usage(input_tokens=1_000, output_tokens=output_tokens)
    return FakeModelClient([ModelResponse(text=text, stop_reason=stop, usage=usage)])


def run(client: FakeModelClient):
    return run_agent(client, "", "Standard promise?", ToolRegistry(2_000), BUDGET, LIMITS)


def test_same_answer_more_reasoning_costs_more() -> None:
    plain = run(answered(output_tokens=40))  # the answer alone
    reasoning = run(answered(output_tokens=3_040))  # the same answer after hidden reasoning
    assert plain.final_text == reasoning.final_text
    assert run_cost(plain, PRICE) == Decimal("0.0012")
    assert run_cost(reasoning, PRICE) == Decimal("0.0162")  # input unchanged, output x76


def test_reasoning_can_spend_the_output_limit_before_the_answer() -> None:
    result = run(answered(output_tokens=4_000, stop="truncated", text=""))
    assert result.cause is StopCause.TRUNCATED
    assert result.final_text == ""
    assert run_cost(result, PRICE) == Decimal("0.021")  # paid for, nothing usable
