"""Hand-built histories for the unit tests and exercises: no model, no network, no key.

The tool data here is short fixture text, not Kestrel records; the loop tests in
test_agent.py use the real mock API.
"""

from ch10.model_client import Message, ModelResponse, ToolCall, ToolResult, Usage
from ch10.state import ConversationState

USAGE = Usage(input_tokens=0, output_tokens=0)


def tool_round(state: ConversationState, calls: list[tuple[str, dict, str]]) -> None:
    """One assistant message with every call, then one message with every result."""
    ids = [f"call_{len(state.messages)}_{n}" for n in range(len(calls))]
    pairs = list(zip(ids, calls, strict=True))
    tool_calls = [ToolCall(id=i, name=name, arguments=args) for i, (name, args, _) in pairs]
    state.add_assistant(
        ModelResponse(text="", stop_reason="tool_call", usage=USAGE, tool_calls=tool_calls)
    )
    state.add_tool_results([ToolResult(tool_call_id=i, content=data) for i, (_, _, data) in pairs])


def reply(state: ConversationState, text: str) -> None:
    state.add_assistant(ModelResponse(text=text, stop_reason="finished", usage=USAGE))


def maya_history(shipment_rows: int = 0) -> ConversationState:
    """Maya's session as fixture text: four questions, one with two parallel calls.
    shipment_rows > 0 adds a final turn whose tool round returns a long shipment list."""
    s = ConversationState.start("Help me with ticket T-000407.")
    tool_round(s, [("get_ticket", {"ticket_id": "T-000407"}, "ticket: where is my order?")])
    reply(s, "The customer asks where order O-0006066 is.")
    s.add_user("Has order O-0006066 shipped?")
    tool_round(s, [  # parallel calls: one assistant message, one results message
        ("get_order", {"order_id": "O-0006066"}, "order: shipped, USD 829.98"),
        ("get_shipment", {"order_id": "O-0006066"}, "shipment: in transit, not late"),
    ])  # fmt: skip
    reply(s, "It shipped and is still in transit.")
    s.add_user("What can we offer the customer?")
    tool_round(s, [("get_policy", {"name": "returns-policy"}, "returns: refunds up to USD 500")])
    reply(s, "A refund above USD 500 needs Finance.")
    if shipment_rows:
        s.add_user("Is Swiftway Parcel late on other shipments?")
        rows = "\n".join(f"S-{n:07d} Swiftway Parcel late" for n in range(shipment_rows))
        tool_round(s, [("list_shipments", {"carrier": "Swiftway Parcel"}, rows)])
    return s


def with_messages(messages: list[Message]) -> ConversationState:
    state = ConversationState.start("Help me with ticket T-000407.")
    state.messages = messages  # bypasses the add_ methods on purpose
    return state
