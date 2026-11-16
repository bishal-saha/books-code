"""The selection check, scored with scripted calls and run end to end on the fake model."""

from ch08.lookups import kestrel_client
from ch08.model_client import ToolCall
from ch08.return_store import ReturnStore
from ch08.scripted import FAKE_BUDGET, FAKE_LIMITS, selector
from ch08.selection_check import load_fixture, run_check, score_first_call
from ch08.tools import GetDeliveryStatusArgs, ListShipmentsArgs

MODELS = {"get_delivery_status": GetDeliveryStatusArgs, "list_shipments": ListShipmentsArgs}


def tc(name: str, **arguments) -> ToolCall:
    return ToolCall(id="toolu_1", name=name, arguments=arguments)


def test_right_tool_with_valid_arguments_scores_true():
    call = tc("get_delivery_status", order_or_ticket_id="T-000281")
    assert score_first_call(call, ["get_delivery_status"], MODELS)


def test_wrong_tool_scores_false():
    call = tc("list_shipments", late=True)
    assert not score_first_call(call, ["get_delivery_status"], MODELS)


def test_right_tool_with_invalid_arguments_scores_false():
    call = tc("get_delivery_status", order_or_ticket_id="42")
    assert not score_first_call(call, ["get_delivery_status"], MODELS)


def test_no_tool_call_scores_false():
    assert not score_first_call(None, ["get_delivery_status"], MODELS)


def test_fixture_entries_name_only_tools_that_exist():
    import httpx
    from ch08.tools_v1 import build_registry_v1

    http = httpx.Client(base_url="http://kestrel.test")
    names = {
        "v1": set(build_registry_v1(http).args_models()),
        "v2": {"get_delivery_status", "list_shipments", "get_ticket", "get_policy",
               "create_return_authorisation"},
    }  # fmt: skip
    for entry in load_fixture():
        for tool_set, tools in entry.expected.items():
            assert set(tools) <= names[tool_set], entry.request


def test_the_fake_run_prints_the_report(kestrel_url, tmp_path):
    lines: list[str] = []
    with kestrel_client(kestrel_url) as http:
        reports = run_check(
            selector(), http, ReturnStore(str(tmp_path / "r.sqlite")), 1,
            FAKE_BUDGET, FAKE_LIMITS, out=lines.append,
        )  # fmt: skip
    v1, v2 = reports
    assert (v1.acceptable, v1.attempts, v1.tool_calls) == (5, 5, [2])
    assert (v2.acceptable, v2.attempts, v2.tool_calls) == (6, 6, [1])
    assert "tool calls to answer" in lines[0]
