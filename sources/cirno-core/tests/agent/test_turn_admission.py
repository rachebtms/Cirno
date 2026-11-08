"""Admission binds a destination without materializing its model checkpoint."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.providers.base import LLMProvider
from cirno_core.session.manager import SessionManager
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy


async def test_internal_routing_does_not_load_the_checkpoint_after_eviction(tmp_path, monkeypatch):
    bus = MessageBus()
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    key = "websocket:worker"
    await sessions.state.get_header(key)
    await sessions.state.update_metadata(key, {"webui": True})
    await sessions.state.discard(key)
    assert sessions.state.peek_metadata(key, include_runtime=False) is None
    route = WebuiTurnRoutePolicy(sessions)
    loop = AgentLoop(
        bus=bus, provider=MagicMock(spec=LLMProvider), model="fixture", workspace=tmp_path,
        session_manager=sessions, turn_delivery_factory=TurnDeliveryFactory(bus, route, route.admit),
    )
    process = AsyncMock(return_value=None)
    monkeypatch.setattr(loop.processing, "process", process)
    read = AsyncMock(side_effect=AssertionError("Routing must not load a complete model checkpoint"))
    monkeypatch.setattr(sessions.state, "read", read)
    try:
        await loop.dispatch.execute(InboundMessage(
            channel="system", sender_id="system", chat_id=key, content="Continue",
            session_key_override=key, input_role="system", metadata={"_internal_continuation": True},
        ), asyncio.Queue())
        process.assert_awaited_once()
        assert process.await_args.kwargs["delivery"].route.publish_lifecycle
        read.assert_not_awaited()
    finally:
        await loop.aclose()
