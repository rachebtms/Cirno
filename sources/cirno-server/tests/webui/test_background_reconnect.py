"""Exercise background completion through real persistence and reconnect projection."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.tools.context import RequestContext
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.transcript import WebUITranscriptRecorder
from cirno_core.session.turn_continuation import maybe_continue_turn
from cirno_core.session.webui_turns import activity
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy
from cirno_server.webui.outbound_delivery import WebUIOutboundDelivery
from cirno_server.webui.session_projection import WebUISessionProjection


@pytest.mark.parametrize("subscribed", [False, True])
@pytest.mark.parametrize("kind", ["heartbeat", "worker-report", "worker-goal"])
async def test_reconnect_does_not_resurrect_completed_background_work(tmp_path, kind, subscribed):
    sessions = SessionManager(tmp_path / "sessions")
    key = "websocket:research" if kind == "worker-goal" else ROUTER_SESSION_KEY
    chat = key.split(":", 1)[1]
    session = await sessions.state.get(key)
    await sessions.state.update_metadata(key, {"webui": True, "title": "Existing conversation"})
    metadata = {"_heartbeat": True} if kind == "heartbeat" else (
        {"_work_report": {"id": "report-1"}} if kind == "worker-report" else {}
    )
    msg = InboundMessage(
        channel="system", sender_id=kind, chat_id=key, session_key_override=key,
        content="Review active work", input_role="user" if kind == "worker-goal" else "system",
        metadata=metadata,
    )
    bus = MessageBus()
    coordinator = WebuiTurnCoordinator(bus, sessions, schedule_background=MagicMock())
    disconnect = coordinator.subscribe()
    policy = WebuiTurnRoutePolicy(sessions)
    factory = TurnDeliveryFactory(bus, route_policy=policy, route_admission=policy.admit)
    projection = WebUISessionProjection(sessions)
    wire = []
    async def send_raw(_connection, raw, **_kwargs):
        wire.append(json.loads(raw))
    transport = MagicMock(webui_send_raw=AsyncMock(side_effect=send_raw))
    transport.webui_recipients.return_value = (object(),) if subscribed else ()
    delivery = WebUIOutboundDelivery(
        transport, media=MagicMock(), transcripts=WebUITranscriptRecorder(sessions),
        temporary_chats=MagicMock(should_persist_transcript=MagicMock(return_value=True)),
        session_projection=projection,
    )
    async def drain():
        while bus.outbound_size:
            await delivery.send(bus.outbound.get_nowait())
    try:
        current = await factory.create(msg, key)
        await current.bind_session_generation(session.generation)
        await current.running(started_at=100)
        await drain()
        assert projection.active_turn_status(chat) is not None
        if kind == "worker-goal":
            session.metadata["goal_state"] = {"status": "active", "objective": "Complete research"}
            ctx = SimpleNamespace(
                msg=msg, session=session, session_key=key, pending_queue=asyncio.Queue(),
                stop_reason="completed", visible_run_started_at=100, all_messages=[],
                final_content="Step done", request_context=RequestContext(
                    channel="websocket", chat_id=chat, turn_id=current.route.turn_id,
                    metadata=current.route.metadata,
                ),
            )
            assert await maybe_continue_turn(ctx, session_metadata=session.metadata)
            await current.complete(None, publish_completion=False)
            current = await factory.create(ctx.pending_queue.get_nowait(), key)
            await current.bind_session_generation(session.generation)
            await current.running(started_at=100)
            await drain()
            assert any(row["event"] == "goal_status" for row in await projection.hydration_events(key, chat))
        await current.complete(None, publish_completion=True)
        await current.idle()
        await drain()
        assert projection.active_turn_status(chat) is None
        assert not any(row["event"] == "goal_status" for row in await projection.hydration_events(key, chat))
        # Subscribe anew as a refreshed tab; the completed lifetime stays absent.
        transport.webui_recipients.return_value = (object(),)
        wire.clear()
        await delivery.hydrate(chat)
        assert not any(row.get("status") == "running" for row in wire)
    finally:
        disconnect()
        activity.clear_websocket_turns(chat)
        await sessions.state.aclose()
