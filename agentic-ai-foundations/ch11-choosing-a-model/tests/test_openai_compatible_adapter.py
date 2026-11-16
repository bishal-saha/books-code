"""The OpenAI-compatible adapter over httpx.MockTransport: hand-written fixtures, no network."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from ch11.agent import run_agent
from ch11.budget import CallLimits, RunBudget, StopCause
from ch11.model_client import Message, ModelError, ToolCall, ToolDefinition, ToolResult
from ch11.openai_compatible_adapter import NOT_JSON, OpenAICompatibleAdapter
from ch11.settings import Settings
from ch11.tools import OrderIdArgs, Tool, ToolRegistry

FIXTURES = Path(__file__).parent / "fixtures"
GET_ORDER = ToolDefinition(
    name="get_order", description="Get one order.", input_schema=OrderIdArgs.model_json_schema()
)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


class Server:
    """Replays responses in order and keeps every request body it received."""

    def __init__(self, *responses: dict | Callable[[], httpx.Response]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.timeouts: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        self.timeouts.append(request.extensions["timeout"])
        item = self.responses.pop(0)
        return item() if callable(item) else httpx.Response(200, json=item)


def adapter_with(server: Server, **kwargs) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        Settings(),
        base_url="https://compat.example.com/v1",
        api_key="test-key",
        model="test-model",
        transport=httpx.MockTransport(server),
        **kwargs,
    )


def ask(server: Server, **kwargs):
    return adapter_with(server, **kwargs).complete(
        "", user("Status of O-0000042?"), 256, [GET_ORDER]
    )


def test_plain_answer() -> None:
    response = ask(Server(fixture("plain_answer.json")))
    assert response.stop_reason == "finished"
    assert response.text.startswith('{"order_id"')
    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 30)


def test_one_tool_call_arguments_are_parsed() -> None:
    response = ask(Server(fixture("one_tool_call.json")))
    assert response.stop_reason == "tool_call"
    assert response.tool_calls == [
        ToolCall(id="call_1", name="get_order", arguments={"order_id": "O-0000042"})
    ]


def test_parallel_calls_keep_their_order() -> None:
    response = ask(Server(fixture("parallel_tool_calls.json")))
    assert [c.arguments["sku"] for c in response.tool_calls] == ["SKU-00042", "SKU-00043"]


def test_malformed_arguments_reach_the_registry_as_an_error() -> None:
    response = ask(Server(fixture("malformed_arguments.json")))
    assert response.stop_reason == "tool_call"
    call = response.tool_calls[0]  # kept, not dropped
    assert NOT_JSON in call.arguments
    result = registry().dispatch(call)
    assert result.is_error and result.content.startswith("Invalid arguments")


def test_invented_parameter_is_a_validation_error() -> None:
    call = ask(Server(fixture("invented_parameter.json"))).tool_calls[0]
    result = registry().dispatch(call)
    assert result.is_error
    assert "include_history: Extra inputs are not permitted" in result.content


def test_arguments_sent_as_an_object_are_accepted() -> None:
    call = ask(Server(fixture("arguments_as_object.json"))).tool_calls[0]
    assert call.arguments == {"order_id": "O-0000042"}


def test_empty_arguments_mean_no_arguments() -> None:
    assert ask(Server(fixture("empty_arguments.json"))).tool_calls[0].arguments == {}


def test_tool_calls_win_over_a_stop_label() -> None:
    assert ask(Server(fixture("tool_calls_with_stop.json"))).stop_reason == "tool_call"


def test_calls_cut_off_by_the_output_limit_are_truncation() -> None:
    assert ask(Server(fixture("tool_calls_cut_off.json"))).stop_reason == "truncated"


def test_unknown_finish_reason_is_other() -> None:
    assert ask(Server(fixture("unknown_finish_reason.json"))).stop_reason == "other"


def test_empty_tool_calls_is_a_plain_text_step() -> None:
    response = ask(Server(fixture("empty_tool_calls.json")))
    assert response.stop_reason == "finished"  # the silent parser mismatch looks like this
    assert response.tool_calls == []


def test_outbound_messages_carry_the_error_flag_as_a_prefix() -> None:
    server = Server(fixture("plain_answer.json"))
    history = [
        *user("Status of O-0000042?"),
        Message(
            role="assistant",
            tool_calls=[ToolCall(id="call_1", name="get_order", arguments={"order_id": "x"})],
        ),
        Message(
            role="user",
            tool_results=[ToolResult(tool_call_id="call_1", content="bad id", is_error=True)],
        ),
    ]
    adapter_with(server).complete("Be brief.", history, 256, [GET_ORDER])
    wire = server.requests[0]["messages"]
    assert [m["role"] for m in wire] == ["system", "user", "assistant", "tool"]
    assert wire[2]["tool_calls"][0]["function"]["arguments"] == '{"order_id": "x"}'
    assert wire[3] == {"role": "tool", "tool_call_id": "call_1", "content": "ERROR: bad id"}


def test_request_body_settings() -> None:
    server = Server(fixture("plain_answer.json"), fixture("plain_answer.json"))
    ask(server)
    ask(server, reasoning_effort="low", max_tokens_param="max_completion_tokens")
    plain, tuned = server.requests
    assert plain["max_tokens"] == 256 and "reasoning_effort" not in plain
    assert "tool_choice" not in plain  # the endpoint's default applies
    assert tuned["max_completion_tokens"] == 256 and tuned["reasoning_effort"] == "low"


def test_per_call_timeout_is_passed_to_httpx() -> None:
    server = Server(fixture("plain_answer.json"))
    adapter_with(server).complete("", user("hi"), 64, timeout=7.5)
    assert server.timeouts[0]["read"] == 7.5


def test_server_error_is_retried_once() -> None:
    server = Server(lambda: httpx.Response(503), fixture("plain_answer.json"))
    assert ask(server).stop_reason == "finished"
    assert len(server.requests) == 2


def test_retries_stop_at_max_retries() -> None:
    server = Server(lambda: httpx.Response(503), lambda: httpx.Response(503))
    with pytest.raises(ModelError) as err:
        ask(server)
    assert err.value.kind == "provider_error" and len(server.requests) == 2


def test_rejected_request_is_not_retried() -> None:
    server = Server(lambda: httpx.Response(400, json={"error": "unknown effort"}))
    with pytest.raises(ModelError) as err:
        ask(server)
    assert err.value.kind == "bad_request" and len(server.requests) == 1


def test_unreadable_body_is_a_model_error() -> None:
    server = Server(lambda: httpx.Response(200, text="<html>gateway</html>"))
    with pytest.raises(ModelError, match="unreadable"):
        ask(server)


def test_count_tokens_is_a_local_estimate() -> None:
    adapter = adapter_with(Server())
    assert adapter.provider_counts is False
    assert adapter.count_tokens("x" * 40, []) == 10  # CHARS_PER_TOKEN defaults to 4


def registry() -> ToolRegistry:
    r = ToolRegistry(max_result_chars=2_000)
    r.register(Tool("get_order", "Get one order.", OrderIdArgs, lambda a: {"status": "shipped"}))
    return r


BUDGET = RunBudget(max_steps=4, max_total_tokens=10_000, max_wall_seconds=60.0)
LIMITS = CallLimits(max_output_tokens=512, timeout_seconds=30.0)


def test_run_agent_over_the_compatible_adapter() -> None:
    server = Server(fixture("one_tool_call.json"), fixture("plain_answer.json"))
    result = run_agent(adapter_with(server), "Be brief.", "Status of O-0000042?",
                       registry(), BUDGET, LIMITS)  # fmt: skip
    assert result.cause is StopCause.FINISHED
    assert [m["role"] for m in server.requests[1]["messages"]][-1] == "tool"
    assert result.steps[0].tool_calls[0].name == "get_order"


def test_a_tool_calls_label_with_no_calls_is_an_unexpected_stop() -> None:
    server = Server(fixture("tool_calls_label_no_calls.json"))
    result = run_agent(adapter_with(server), "", "Status?", registry(), BUDGET, LIMITS)
    assert result.cause is StopCause.UNEXPECTED_STOP
