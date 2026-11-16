import math

import pytest
from ch02.tokens import CHARS_PER_TOKEN, TokenCountError, count_text, load_page


def test_counted_figure_comes_from_the_provider(settings, fake_client):
    page = load_page(settings, "returns-policy.md")
    result = count_text(settings, "returns-policy.md", page, fake_client(count=123))
    assert result.counted_tokens == 123  # whatever count_tokens reported
    assert result.heuristic_tokens == math.ceil(len(page) / CHARS_PER_TOKEN)


def test_no_key_gives_an_estimate_not_a_count(settings_without_key):
    page = load_page(settings_without_key, "returns-policy.md")
    result = count_text(settings_without_key, "returns-policy.md", page)
    assert result.counted_tokens is None
    assert result.heuristic_tokens > 0


def test_missing_page_says_how_to_fix_it(settings):
    with pytest.raises(FileNotFoundError, match="kestrel up"):
        load_page(settings, "no-such-page.md")


def test_provider_error_names_the_page(settings, fake_client):
    import anthropic
    import httpx

    client = fake_client()
    request = httpx.Request("POST", "https://example.com/v1/messages/count_tokens")

    def fail(**_):
        raise anthropic.APIConnectionError(request=request)

    client.messages.count_tokens = fail
    with pytest.raises(TokenCountError, match="returns-policy.md"):
        count_text(settings, "returns-policy.md", "text", client)
