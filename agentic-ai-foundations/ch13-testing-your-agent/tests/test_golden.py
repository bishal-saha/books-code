"""The golden-task file: it loads, it rejects mistakes, and its facts match the seeded data."""

import httpx
import pytest
from ch13.golden import GoldenTask, check_tool_names, load_golden_tasks
from pydantic import ValidationError


def test_the_shipped_file_loads_and_names_real_tools(registry):
    tasks = load_golden_tasks()
    assert len(tasks) == 6
    check_tool_names(tasks, {d.name for d in registry.definitions()})


def test_a_misspelt_field_is_an_error():
    with pytest.raises(ValidationError, match="requried_facts"):
        GoldenTask(id="x", input="q", max_steps=2, requried_facts=[{"value": "NEEDS INFO"}])


def test_an_unknown_tool_is_caught_before_any_trial():
    task = GoldenTask(id="x", input="q", max_steps=2, required_any_tool=["count_late"])
    with pytest.raises(ValueError, match="no tool named 'count_late'"):
        check_tool_names([task], {"list_shipments"})


def test_expected_facts_match_the_seeded_api(kestrel_url):
    """If the kestrel seed changes, this fails: regenerate the facts, never grade stale ones."""
    api = httpx.Client(base_url=kestrel_url)
    shipment = api.get("/orders/O-0000107/shipment").json()
    stock = api.get("/stock/SKU-00042").json()
    ticket = api.get("/tickets/T-000042").json()
    actual = {
        "order-status": {"status": api.get("/orders/O-0000042").json()["status"]},
        "shipment-late": {"carrier": shipment["carrier"], "late": shipment["late"]},
        "stock-total": {"total_on_hand": sum(w["on_hand"] for w in stock["warehouses"])},
        "ticket-order": {"order_id": ticket["order_id"], "priority": ticket["priority"]},
    }
    for task in load_golden_tasks():
        for fact in task.required_facts:
            if fact.field:
                assert actual[task.id][fact.field] == fact.value, (task.id, fact.field)
    assert api.get("/orders/O-9999999").status_code == 404
    late = api.get("/shipments", params={"late": "true", "limit": 21}).json()
    assert len(late) == 21  # more late shipments exist than list_shipments can return
    for carrier in {s["carrier"] for s in late}:  # per carrier, too: every page comes back full
        params = {"late": "true", "limit": 21, "carrier": carrier}
        assert len(api.get("/shipments", params=params).json()) == 21, carrier
