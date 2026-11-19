"""Text deduplication must not discard a changed artifact or structured event."""

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import UserInputEvent
from cirno_server.channels.delivery.duplicates import OriginReplies


def reply(content, **kwargs):
    return OutboundMessage("fixture", "chat", content,
                           metadata={"origin_message_id": "origin"}, **kwargs)


@pytest.mark.parametrize("changed", [
    "```python\nif ready:\n    run()\nfinish()\n```",
    "```python\nif ready:\n\trun()\n    finish()\n```",
    "```python\nif ready:\n    run()\n\n    finish()\n```",
])
def test_code_whitespace_changes_are_not_duplicates(changed):
    origins = OriginReplies()
    original = "```python\nif ready:\n    run()\n    finish()\n```"
    assert not origins.matches(reply(original))
    assert not origins.matches(reply(changed)), "Code whitespace was collapsed before comparison"
    assert origins.matches(reply(changed)), "Identical plain replies should still be suppressed"


@pytest.mark.parametrize("payload", [
    {"media": ["/tmp/new-report.pdf"]}, {"buttons": [["Approve", "Reject"]]},
    {"reply_to": "new-target"},
    {"event": UserInputEvent(content="Result ready", created_at_ms=1, provenance={})},
])
def test_changed_nontext_payload_is_never_suppressed_by_its_caption(payload):
    origins = OriginReplies()
    assert not origins.matches(reply("Result ready"))
    assert not origins.matches(reply("Result ready", **payload))
    # File paths can be reused after regeneration; a caption is insufficient
    # evidence to discard even another attachment at exactly the same path.
    assert not origins.matches(reply("Result ready", **payload))


@pytest.mark.parametrize("metadata", [
    {"_agent_ui": {"kind": "decision", "id": "new"}},
    {"_telegram_action_url": "https://fixture.test/new-action"},
    {"render_as": "text"},
])
def test_rich_presentation_is_not_a_plain_text_duplicate(metadata):
    origins = OriginReplies()
    assert not origins.matches(reply("Result ready"))
    msg = reply("Result ready")
    msg.metadata.update(metadata)
    assert not origins.matches(msg)
