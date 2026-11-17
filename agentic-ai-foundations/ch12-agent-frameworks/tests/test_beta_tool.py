"""@beta_tool in the pinned SDK, offline: the schema it builds and how a bad call fails."""

import pytest
from ch12.beta_tool_demo import ID_PATTERN, get_delivery_status


def test_schema_keeps_the_docstring_and_the_pattern():
    schema = get_delivery_status.to_dict()["input_schema"]
    field = schema["properties"]["order_or_ticket_id"]
    assert field["pattern"] == ID_PATTERN
    assert field["description"].startswith("The id the user gave")
    assert schema["required"] == ["order_or_ticket_id"]


def test_a_bad_id_raises_instead_of_returning_a_result():
    with pytest.raises(ValueError, match="Invalid arguments"):
        get_delivery_status.call({"order_or_ticket_id": "42"})
