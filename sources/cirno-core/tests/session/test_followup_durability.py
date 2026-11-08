"""An acknowledged follow-up must have a durable replay record."""

import pytest

from cirno_core.bus.events import InboundMessage
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.pending import pending_followups


@pytest.mark.parametrize("origin", ["owner", "heartbeat"])
@pytest.mark.parametrize("invalid", ["set", "circular"])
async def test_invalid_followup_metadata_rejects_without_committing(tmp_path, origin, invalid):
    manager = SessionManager(tmp_path)
    state = manager.state
    key = "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
    original = await state.get(key)
    revision = original.revision
    malformed = {1, 2} if invalid == "set" else []
    if invalid == "circular":
        malformed.append(malformed)
    metadata = {"bad": malformed, **({"_heartbeat": True} if origin == "heartbeat" else {})}
    message = InboundMessage(
        channel="system" if origin == "heartbeat" else "websocket",
        sender_id="heartbeat" if origin == "heartbeat" else "owner",
        chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", content="must not disappear", metadata=metadata,
    )
    try:
        with pytest.raises(TypeError if invalid == "set" else ValueError):
            await state.queue_followup(key, message)
        unchanged = await state.read(key)
        assert unchanged.revision == revision
        assert unchanged.metadata == original.metadata
        assert pending_followups(unchanged) == []
        message.metadata = {"_heartbeat": True} if origin == "heartbeat" else {}
        identifier = await state.queue_followup(key, message)
        assert identifier is not None
    finally:
        await state.aclose()

    reopened = SessionManager(tmp_path).state
    try:
        recovered = pending_followups(await reopened.get(key))
        assert [item.content for item in recovered] == ["must not disappear"]
        await reopened.acknowledge_followups(key, [identifier])
        assert pending_followups(await reopened.get(key)) == []
    finally:
        await reopened.aclose()
