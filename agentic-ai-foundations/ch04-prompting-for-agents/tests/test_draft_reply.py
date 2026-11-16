"""draft_reply against the fake model: the request reaches the client unchanged."""

from ch04.fake_model import FakeModelClient
from ch04.prompt_builder import TicketData, build_messages, draft_reply, load_prompt


def test_request_reaches_client_unchanged_and_version_is_recorded(make_ticket):
    prompt, ticket, data = load_prompt("support_reply", 2), make_ticket(), TicketData()
    fake = FakeModelClient(replies=["Subject: Your chair\nReply:\nHi.\nNotes for reviewer: none"])

    draft = draft_reply(fake, prompt, ticket, data, max_tokens=400)

    assert fake.calls[0].system == prompt.body
    assert fake.calls[0].messages == build_messages(ticket, data)
    assert fake.calls[0].max_tokens == 400
    assert (draft.ticket_id, draft.prompt_version) == ("T-999999", 2)
