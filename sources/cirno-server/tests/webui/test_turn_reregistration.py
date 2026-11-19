"""An automatic slice must retain earlier transcript persistence failures."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.turn_delivery import TurnRoute
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.bus.outbound_events import TurnEndEvent
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.transcript import WEBUI_TRANSCRIPT_INCOMPLETE_KEY, WebUITranscriptRecorder
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)
from cirno_core.session.webui_turns import activity
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy
from cirno_server.webui.outbound_delivery import WebUIOutboundDelivery


@pytest.mark.parametrize("continuation", [False, True])
async def test_running_reregistration_keeps_failed_answer_recoverable(history, monkeypatch, continuation):
    chat_id = "slice-persistence"
    key = "websocket:" + chat_id
    history.append(key, {"event": "user", "text": "Task", "turn_id": "same-turn"})
    metadata = await history.metadata(chat_id, {
        "webui": True, WEBUI_TURN_METADATA_KEY: "same-turn", WEBSOCKET_TURN_OWNER_METADATA_KEY: "same-owner",
    })
    output = WebUIOutboundDelivery(
        SimpleNamespace(webui_recipients=lambda _audience: ()), media=SimpleNamespace(),
        transcripts=WebUITranscriptRecorder(history.sessions),
        temporary_chats=SimpleNamespace(should_persist_transcript=lambda _chat: True),
        session_projection=SimpleNamespace(),
    )
    original_append = history.sessions.state.append_history
    calls = 0

    async def append(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated failed answer write")
        return await original_append(*args, **kwargs)

    monkeypatch.setattr(history.sessions.state, "append_history", append)
    bus = SimpleNamespace(publish_outbound=AsyncMock())
    msg = InboundMessage(channel="websocket", sender_id="u", chat_id=chat_id, content="Task", metadata=metadata)
    try:
        await activity.publish_turn_run_status(bus, msg, "running", started_at=12.5)
        await output.send_delta(chat_id, "Answer not saved", metadata, stream_end=True, stream_id="first")
        assert activity.websocket_turn_transcript_persistence_failed(chat_id, "same-owner")
        if continuation:
            next_input = InboundMessage(
                channel="system", sender_id="system:continuation", chat_id=chat_id, content="Continue",
                metadata={**metadata, "_internal_continuation": True},
            )
            sessions = SimpleNamespace(state=SimpleNamespace(read_metadata=AsyncMock(return_value={"metadata": {"webui": True}})))
            route = await WebuiTurnRoutePolicy(sessions)(next_input, key, TurnRoute("websocket", chat_id, {}))
            assert route.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] == "same-owner"
            msg.metadata = {**route.metadata, HISTORY_GENERATION_METADATA_KEY: metadata[HISTORY_GENERATION_METADATA_KEY]}
        await activity.publish_turn_run_status(bus, msg, "running", started_at=12.5)
        await output.send(OutboundMessage(channel="websocket", chat_id=chat_id, content="", event=TurnEndEvent(), metadata=msg.metadata))
        terminal = next(record for record in history.read(key) if record.get("event") == "turn_end")
        assert terminal.get(WEBUI_TRANSCRIPT_INCOMPLETE_KEY) is True
        assert activity.websocket_turn_wall_started_at(chat_id) is None
    finally:
        activity.clear_websocket_turns(chat_id)


@pytest.mark.parametrize("changed_key", [WEBSOCKET_TURN_OWNER_METADATA_KEY, WEBUI_TURN_METADATA_KEY, HISTORY_GENERATION_METADATA_KEY])
async def test_new_lifecycle_does_not_inherit_another_failure(changed_key):
    chat_id = "fresh-persistence"
    bus = SimpleNamespace(publish_outbound=AsyncMock())
    metadata = {WEBSOCKET_TURN_OWNER_METADATA_KEY: "owner", WEBUI_TURN_METADATA_KEY: "turn", HISTORY_GENERATION_METADATA_KEY: "generation"}
    msg = InboundMessage(channel="websocket", sender_id="u", chat_id=chat_id, content="Task", metadata=metadata)
    try:
        await activity.publish_turn_run_status(bus, msg, "running", started_at=12.5)
        assert activity.mark_websocket_turn_transcript_persistence_failed(chat_id, "owner")
        msg.metadata = {**metadata, changed_key: "new-value"}
        await activity.publish_turn_run_status(bus, msg, "running", started_at=15.0)
        assert not activity.websocket_turn_transcript_persistence_failed(chat_id, msg.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY])
    finally:
        activity.clear_websocket_turns(chat_id)
