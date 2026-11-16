from ch02.cost import PER_MILLION
from ch02.reasoning import ask
from ch02.tokens import load_page


def run(settings, fake_client, fixture, effort="high"):
    client = fake_client(count=230, responses=fixture)
    page = load_page(settings, "returns-policy.md")
    return client, ask(client, settings, page, effort, max_tokens=2_000)


def test_reasoning_tokens_are_billed_as_output(settings, fake_client):
    _, result = run(settings, fake_client, "reasoning_high.json")
    assert result.thinking_blocks == 1
    assert result.thinking_tokens == 890
    assert result.output_tokens > result.thinking_tokens  # the answer is the small part
    price = settings.output_price_per_mtok
    assert result.cost.output_cost == result.output_tokens * price / PER_MILLION
    assert "Finance" in result.answer
    assert result.truncated is False


def test_effort_and_thinking_go_in_the_request(settings, fake_client):
    client, _ = run(settings, fake_client, "reasoning_low.json", effort="low")
    request = client.requests[0]
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "low"}
    assert "temperature" not in request


def test_limit_hit_is_flagged_as_a_failure(settings, fake_client):
    _, result = run(settings, fake_client, "reasoning_truncated.json")
    assert result.truncated is True
    assert result.answer == ""  # the cap was spent on reasoning before any answer
