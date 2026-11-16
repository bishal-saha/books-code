"""Scripted fake-model configurations for `compare_models --fake` and the tests.

The model's side (tool calls, answers and token counts) is written by hand and labelled fake;
the prices are illustrative, not any seller's. Tool results are real: the registry calls the
seeded Kestrel API. `fake-correct` makes the right calls and answers correctly.
`fake-wrong-tool` calls a tool that cannot answer, then gives the right answer anyway.
"""

import json
from datetime import date
from decimal import Decimal

import httpx

from ch11.configs import ModelConfig, Price, make_client
from ch11.fake_model import FakeModelClient
from ch11.model_client import ModelResponse, ToolCall, Usage
from ch11.settings import Settings
from ch11.tasks import Task

ILLUSTRATIVE = Price(
    input_per_mtok=Decimal("1.00"),
    output_per_mtok=Decimal("5.00"),
    as_of=date(2026, 11, 16),
    source_url="illustrative price for the fake model, not a real seller's",
)

FAKE_CONFIGS = [
    ModelConfig(name=name, provider="anthropic", model_env="-", api_key_env="-", price=ILLUSTRATIVE)
    for name in ("fake-correct", "fake-wrong-tool")
] + [
    ModelConfig(
        name="local-server",  # always skipped in --fake mode: shows the "not configured" path
        provider="openai_compatible",
        model_env="LOCAL_COMPAT_MODEL",
        api_key_env="LOCAL_COMPAT_API_KEY",
        base_url_env="LOCAL_COMPAT_BASE_URL",
    ),
]

RIGHT_CALLS: dict[str, list[tuple[str, dict]]] = {  # one step; several calls run in parallel
    "order-status": [("get_order", {"order_id": "O-0000042"})],
    "order-carrier": [
        ("get_order", {"order_id": "O-0000108"}),
        ("get_shipment", {"order_id": "O-0000108"}),
    ],
    "most-stock": [("get_stock", {"sku": "SKU-00042"}), ("get_stock", {"sku": "SKU-00043"})],
    "ticket-triage": [("get_ticket", {"ticket_id": "T-000042"})],
    "outdated-policy": [("get_policy", {"name": "shipping-policy"})],
    "shipment-plus-policy": [
        ("get_shipment", {"order_id": "O-0000107"}),
        ("get_policy", {"name": "shipping-policy"}),
    ],
}
WRONG_CALLS = [("list_policies", {})]  # answers nothing any task asks


def scripted_run(calls: list[tuple[str, dict]], answer: str) -> FakeModelClient:
    tool_calls = [
        ToolCall(id=f"call_fake_{n}", name=name, arguments=args)
        for n, (name, args) in enumerate(calls, 1)
    ]
    return FakeModelClient(
        [
            ModelResponse(  # invented token counts, identical for every script
                text="",
                stop_reason="tool_call",
                usage=Usage(input_tokens=1_200, output_tokens=80),
                tool_calls=tool_calls,
            ),
            ModelResponse(
                text=answer,
                stop_reason="finished",
                usage=Usage(input_tokens=1_800, output_tokens=60),
            ),
        ]
    )


def fake_clients(api: httpx.Client, settings: Settings):
    def factory(config: ModelConfig):
        if config.name not in ("fake-correct", "fake-wrong-tool"):
            make_client(config, settings, env={})  # raises ConfigError: nothing is configured
        calls_for = (
            (lambda task: RIGHT_CALLS[task.task_id])
            if config.name == "fake-correct"
            else (lambda task: WRONG_CALLS)
        )

        def client_for(task: Task) -> FakeModelClient:  # a fresh script for every run
            return scripted_run(calls_for(task), json.dumps(task.expected(api)))

        return client_for

    return factory
