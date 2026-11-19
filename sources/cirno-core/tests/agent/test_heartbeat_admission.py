"""Heartbeat admission settles against current Router state, not an earlier read."""

import asyncio

import pytest

from cirno_core.bus.queue import MessageBus
from cirno_core.runtime.heartbeat import discard_paused_heartbeat, enqueue_heartbeat
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.pending import pending_followups
from cirno_core.session.router_session import ensure_router_session


@pytest.fixture
async def router(tmp_path):
    sessions = SessionManager(tmp_path)
    await ensure_router_session(sessions)
    yield sessions, MessageBus()
    await sessions.state.aclose()


async def test_concurrent_heartbeat_checks_enqueue_only_once(router, monkeypatch):
    sessions, bus = router
    queue = sessions.state.queue_followup
    ready = asyncio.Event()
    arrivals = 0

    async def after_check(key, message):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await ready.wait()
        return await queue(key, message)

    monkeypatch.setattr(sessions.state, "queue_followup", after_check)
    async with asyncio.timeout(2):
        outcomes = await asyncio.gather(
            enqueue_heartbeat(sessions, bus, "First tick"),
            enqueue_heartbeat(sessions, bus, "Second tick"),
        )
    assert sorted(outcomes) == [False, True]
    assert bus.inbound_size == 1
    assert len(pending_followups(await sessions.state.read(ROUTER_SESSION_KEY))) == 1


@pytest.mark.parametrize("change", ["pause", "reset"])
async def test_heartbeat_rechecks_state_at_journal_commit(router, monkeypatch, change):
    sessions, bus = router
    queue = sessions.state.queue_followup

    async def after_check(key, message):
        if change == "pause":
            await sessions.state.update_metadata(key, {"heartbeat_paused": True})
        else:
            await sessions.state.reset(key)
        return await queue(key, message)

    monkeypatch.setattr(sessions.state, "queue_followup", after_check)
    assert not await enqueue_heartbeat(sessions, bus, "Obsolete tick")
    assert bus.inbound_size == 0
    assert not pending_followups(await sessions.state.read(ROUTER_SESSION_KEY))


async def test_discarded_heartbeat_does_not_consume_replacement_followup(router):
    from cirno_core.bus.events import InboundMessage
    from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY

    sessions, bus = router
    assert await enqueue_heartbeat(sessions, bus, "Old tick")
    old = await bus.consume_inbound()
    await sessions.state.reset(ROUTER_SESSION_KEY)
    await sessions.state.update_metadata(ROUTER_SESSION_KEY, {"heartbeat_paused": True})
    await sessions.state.queue_followup(ROUTER_SESSION_KEY, InboundMessage(
        "websocket", "owner", ROUTER_SESSION_KEY.split(":", 1)[1], "New owner request",
        metadata={PENDING_FOLLOWUP_ID_KEY: old.metadata[PENDING_FOLLOWUP_ID_KEY]},
    ))
    assert await discard_paused_heartbeat(sessions, old)
    assert [item.content for item in pending_followups(await sessions.state.read(ROUTER_SESSION_KEY))] == [
        "New owner request",
    ]
