"""One raw SDK call, to see the response's shape. The CLI does not use this file."""

import anthropic

from ch03.settings import Settings
from ch03.ticket_prompt import SYSTEM_PROMPT, build_user_text, fetch_ticket

settings = Settings.from_env()
assert settings.api_key is not None, "set ANTHROPIC_API_KEY in .env"
ticket = fetch_ticket(settings.kestrel_url, "T-000407")

client = anthropic.Anthropic(api_key=settings.api_key.get_secret_value())
response = client.messages.create(
    model=settings.model,  # from .env, never a literal
    max_tokens=settings.max_output_tokens,
    system=SYSTEM_PROMPT,  # a parameter, not a message
    messages=[{"role": "user", "content": build_user_text(ticket)}],
)
print(response.content)  # a list of blocks, not a string
print(response.stop_reason)  # why generation ended
print(response.usage)  # token counts
