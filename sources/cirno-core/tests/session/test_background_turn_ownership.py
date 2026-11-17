"""Background work and its automatic slices own one visible run lifetime."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.agent.tools.context import RequestContext
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.turn_continuation import maybe_continue_turn
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY as OWNER,
    WEBUI_TURN_METADATA_KEY as TURN,
)
from cirno_core.session.webui_turns import activity
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy


@pytest.mark.parametrize("kind", ["heartbeat", "worker-report"])
async def test_router_background_input_has_matching_visible_lifecycle(tmp_path, kind):
    sessions = SessionManager(tmp_path)
    factory = TurnDeliveryFactory(MessageBus(), route_policy=WebuiTurnRoutePolicy(sessions))
    metadata = {"_heartbeat": True} if kind == "heartbeat" else {"_work_report": {"id": "report-1"}}
    msg = InboundMessage(channel="system", sender_id=kind, chat_id=ROUTER_SESSION_KEY,
                         content="Review active work", input_role="system", metadata=metadata)
    delivery = await factory.create(msg, ROUTER_SESSION_KEY)
    assert delivery.route.publish_lifecycle
    assert delivery.lifecycle_message.channel == "websocket"
    assert delivery.lifecycle_message.metadata[TURN] == delivery.route.turn_id
    await sessions.state.aclose()


@pytest.mark.parametrize("channel", ["system", "websocket"])
async def test_continuation_reuses_registered_owner_and_original_turn(tmp_path, channel):
    sessions = SessionManager(tmp_path)
    key = "websocket:background-worker"
    await sessions.state.get_header(key)
    await sessions.state.update_metadata(key, {"webui": True})
    factory = TurnDeliveryFactory(MessageBus(), route_policy=WebuiTurnRoutePolicy(sessions))
    msg = InboundMessage(channel=channel, sender_id="user", chat_id=key if channel == "system" else "background-worker",
                         content="Work until complete", input_role="user", session_key_override=key,
                         metadata={TURN: "user-turn"} if channel == "websocket" else {})
    first = await factory.create(msg, key)
    bus = MagicMock(publish_outbound=AsyncMock())
    await activity.publish_turn_run_status(bus, first.lifecycle_message, "running", started_at=100)
    try:
        session = await sessions.state.get(key)
        session.metadata["goal_state"] = {"status": "active", "objective": "Finish the work"}
        pending = asyncio.Queue()
        ctx = SimpleNamespace(
            session=session, msg=msg, session_key=key, pending_queue=pending,
            stop_reason="completed", visible_run_started_at=100, final_content="Step complete",
            all_messages=[], request_context=RequestContext(
                channel=first.route.channel, chat_id=first.route.chat_id,
                turn_id=first.route.turn_id, metadata=first.route.metadata,
            ),
        )
        assert await maybe_continue_turn(ctx, session_metadata=session.metadata)
        followup = pending.get_nowait()
        second = await factory.create(followup, key)
        assert second.route.turn_id == first.route.turn_id
        assert second.route.metadata[OWNER] == first.route.metadata[OWNER]
        await activity.publish_turn_run_status(bus, second.lifecycle_message, "running", started_at=100)
        assert activity.clear_websocket_turn_if_current("background-worker", second.route.metadata[OWNER])
        assert activity.websocket_turn_wall_started_at("background-worker") is None
        # A genuinely independent input must still acquire its own lifetime.
        independent = await factory.create(msg, key)
        assert independent.route.metadata[OWNER] != first.route.metadata[OWNER]
    finally:
        activity.clear_websocket_turns("background-worker")
        await sessions.state.aclose()


@pytest.mark.parametrize("kind", ["heartbeat", "worker-report"])
async def test_background_router_execution_publishes_terminal_events(tmp_path, kind):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.bus.outbound_events import GoalStatusEvent, TurnEndEvent
    from cirno_core.providers.contracts import LLMResponse
    from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
    from sources.development.testing.sessions import run_session

    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content="No update needed."))
    bus = MessageBus()
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")
    loop.turn_delivery_factory.route_policy = WebuiTurnRoutePolicy(loop.sessions)
    coordinator = WebuiTurnCoordinator(bus=bus, sessions=loop.sessions,
                                      schedule_background=loop.schedule_background)
    disconnect = coordinator.subscribe()
    metadata = {"_heartbeat": True} if kind == "heartbeat" else {"_work_report": {"id": "report-1"}}
    try:
        await run_session(loop, InboundMessage(
            channel="system", sender_id=kind, chat_id=ROUTER_SESSION_KEY,
            session_key_override=ROUTER_SESSION_KEY,
            content="Check active work; remain quiet if no update is needed.",
            input_role="system", metadata=metadata,
        ))
        outbound = [bus.outbound.get_nowait() for _ in range(bus.outbound_size)]
        statuses = [row for row in outbound if isinstance(row.event, GoalStatusEvent)]
        assert [row.event.status for row in statuses] == ["running", "idle"]
        terminal = [row for row in outbound if isinstance(row.event, TurnEndEvent)]
        assert len(terminal) == 1
        assert len({row.metadata[TURN] for row in [*statuses, *terminal]}) == 1
        assert len({row.metadata[OWNER] for row in [*statuses, *terminal]}) == 1
    finally:
        disconnect()
        activity.clear_websocket_turns(ROUTER_SESSION_KEY.split(":", 1)[1])
        await loop.sessions.state.aclose()
