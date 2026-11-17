"""What @beta_tool in the pinned anthropic 2.8 builds from a function. No key, no network.

uv run python -m ch12.beta_tool_demo

The SDK is already a dependency; nothing is installed for this chapter. The description and
the id pattern are Chapter 8's, so you can compare the schema with GetDeliveryStatusArgs.
"""

import json
from typing import Annotated

from anthropic import beta_tool
from pydantic import Field

from ch12.tools import GetDeliveryStatusArgs

ID_PATTERN = r"^(O-\d{7}|T-\d{6})$"


@beta_tool
def get_delivery_status(
    order_or_ticket_id: Annotated[str, Field(pattern=ID_PATTERN)],
) -> str:
    """Returns delivery status for one order.

    Args:
        order_or_ticket_id: The id the user gave: an order id (O-0013833) or a ticket id.
    """
    return json.dumps({"order_or_ticket_id": order_or_ticket_id})


def main() -> None:
    schema = get_delivery_status.to_dict()["input_schema"]
    print("schema from @beta_tool:")
    print(json.dumps(schema["properties"], indent=2))
    ours = GetDeliveryStatusArgs.model_json_schema()["properties"]
    print(
        "pattern kept:",
        schema["properties"]["order_or_ticket_id"]["pattern"]
        == ours["order_or_ticket_id"]["pattern"],
    )
    try:
        get_delivery_status.call({"order_or_ticket_id": "42"})
    except ValueError as exc:
        print(f"call with a bad id raises {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
