"""System follow-ups retain one identity across live delivery and restart."""
import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import get_home_path
from cirno_core.providers.generation import GenerationSettings
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.recovery.pending import pending_followups, record_pending_followup
from cirno_core.session.router_session import ensure_router_session
from cirno_core.session.sqlite_store import SessionConflictError


def wake():
    return InboundMessage(channel="websocket", sender_id="system:awakening", chat_id=ROUTER_CHAT_ID,
        input_role="system", session_key_override=ROUTER_SESSION_KEY,
        content="First introduction", metadata={PENDING_FOLLOWUP_ID_KEY: "first-awakening", "_awakening": True})


async def test_system_receipt_survives_acknowledgement_and_restart(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    reopened = None
    try:
        await ensure_router_session(sessions)
        message = wake()
        assert await sessions.state.queue_followup(ROUTER_SESSION_KEY, message) == "first-awakening"
        await sessions.state.acknowledge_followups(ROUTER_SESSION_KEY, ["first-awakening"])
        reopened = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
        assert await reopened.state.queue_followup(ROUTER_SESSION_KEY, message) is None
        with pytest.raises(SessionConflictError, match="different content"):
            await reopened.state.queue_followup(ROUTER_SESSION_KEY, replace(message, content="Changed payload"))
    finally:
        if reopened: await reopened.state.aclose()
        await sessions.state.aclose()


async def test_duplicate_wake_during_active_turn_is_not_injected_again(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.home._instance_path", tmp_path / "instance")
    provider = MagicMock(aclose=AsyncMock())
    provider.generation = GenerationSettings()
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path / "workspace")
    entered, release = asyncio.Event(), asyncio.Event()
    async def execute(message, pending):
        entered.set()
        await release.wait()
    monkeypatch.setattr(loop.dispatch, "execute", execute)
    try:
        await ensure_router_session(loop.sessions)
        message = wake()
        await loop.sessions.state.queue_followup(ROUTER_SESSION_KEY, message)
        await loop.dispatch.receive(message)
        async with asyncio.timeout(5): await entered.wait()
        await loop.dispatch.receive(wake())
        await loop.dispatch.receive(wake())
        assert loop._pending_queues[ROUTER_SESSION_KEY].empty()
    finally:
        release.set()
        await asyncio.gather(*loop._active_tasks.get(ROUTER_SESSION_KEY, set()))
        await loop.aclose()


@pytest.mark.parametrize("completed", [False, True])
async def test_legacy_pending_wake_obeys_completed_bootstrap_without_changing_history(tmp_path, monkeypatch, completed):
    monkeypatch.setattr("cirno_core.config.home._instance_path", tmp_path / "instance")
    home = get_home_path(); home.mkdir(parents=True, exist_ok=True)
    (home / "BOOTSTRAP.md").write_text("" if completed else "Introduce yourself")
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    bus = MessageBus()
    try:
        legacy = sessions.get_or_create(ROUTER_SESSION_KEY)
        legacy.add_message("user", "Old first-awakening input")
        legacy.add_message("assistant", "Hello, what should I call you?")
        record_pending_followup(legacy, wake())
        sessions.save(legacy)
        await ensure_router_session(sessions)
        human = InboundMessage(channel="websocket", sender_id="owner", chat_id=ROUTER_CHAT_ID, content="Read this paper")
        await sessions.state.queue_followup(ROUTER_SESSION_KEY, human)
        # Simulate the old journal, which predates durable system receipts.
        prior = await sessions.state.read(ROUTER_SESSION_KEY)
        await RecoveryCoordinator(sessions, bus).scan()
        delivered = [await bus.consume_inbound() for _ in range(bus.inbound_size)]
        assert [row.content for row in delivered] == (["Read this paper"] if completed else ["First introduction", "Read this paper"])
        restored = await sessions.state.read(ROUTER_SESSION_KEY)
        assert restored.messages == prior.messages
        if completed:
            assert await sessions.state.queue_followup(ROUTER_SESSION_KEY, wake()) is None
        assert [row.content for row in pending_followups(restored)] == [row.content for row in delivered]
    finally:
        await sessions.state.aclose()
