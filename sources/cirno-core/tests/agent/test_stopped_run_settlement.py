"""Stopping queued/obsolete work must settle its admitted browser lifecycle."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.outbound_events import GoalStatusEvent, TurnEndEvent
from cirno_core.bus.queue import MessageBus
from cirno_core.session.manager import SessionManager
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)
from cirno_core.session.webui_turns.activity import (
    clear_websocket_turns,
    register_queued_websocket_turn_if_idle,
)
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy


def runtime(tmp_path, text, *, continuation=False):
    bus = MessageBus()
    sessions = SessionManager(tmp_path)
    provider = MagicMock(aclose=AsyncMock())
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model='fixture',
                     session_manager=sessions, turn_delivery_factory=TurnDeliveryFactory(bus, WebuiTurnRoutePolicy(sessions)))
    chat = 'stopped-settlement'
    clear_websocket_turns(chat)
    owner = register_queued_websocket_turn_if_idle(chat, 'admitted-turn')
    msg = InboundMessage(channel='websocket', sender_id='user', chat_id=chat, content=text,
                         metadata={'webui':True, WEBUI_TURN_METADATA_KEY:'admitted-turn', WEBSOCKET_TURN_OWNER_METADATA_KEY:owner,
                                   **({'_internal_continuation':True, '_internal_continuation_kind':'sustained_goal', '_goal_id':'old-goal'} if continuation else {})})
    return loop, bus, msg, WebuiTurnCoordinator(bus, sessions, loop.schedule_background)


async def assert_settled(bus, msg):
    messages = []
    while bus.outbound_size:
        messages.append(await bus.consume_outbound())
    assert any(isinstance(row.event, TurnEndEvent) for row in messages)
    assert any(isinstance(row.event, GoalStatusEvent) and row.event.status == 'idle' for row in messages)
    # The WebSocket outbound adapter owns clearing this reservation. It needs
    # the original owner/turn identities on both terminal notifications.
    for row in messages:
        if isinstance(row.event, (TurnEndEvent, GoalStatusEvent)):
            assert row.metadata[WEBUI_TURN_METADATA_KEY] == msg.metadata[WEBUI_TURN_METADATA_KEY]
            assert row.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] == msg.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY]
    clear_websocket_turns(msg.chat_id)


@pytest.mark.parametrize('text', ['Continue the research task', '/consolidate'])
async def test_stop_before_worker_first_step_settles_reserved_turn(tmp_path, text):
    loop, bus, msg, coordinator = runtime(tmp_path, text)
    queue = asyncio.Queue()
    queue.put_nowait(msg)
    loop._pending_queues[msg.session_key] = queue
    try:
        with coordinator.connected():
            await loop.cancel_session_work(msg.session_key, stop_goal=False)
        await assert_settled(bus, msg)
    finally:
        await loop.aclose()


async def test_stop_while_waiting_for_execution_slot_settles_reserved_turn(tmp_path):
    loop, bus, msg, coordinator = runtime(tmp_path, 'Read the assigned papers')
    gate = asyncio.Semaphore(0)
    entered = asyncio.Event()
    acquire = gate.acquire
    async def wait():
        entered.set()
        return await acquire()
    gate.acquire = wait
    loop._concurrency_gate = gate
    try:
        with coordinator.connected():
            await loop.dispatch.receive(msg)
            await asyncio.wait_for(entered.wait(), 5)
            await loop.cancel_session_work(msg.session_key, stop_goal=False)
        await assert_settled(bus, msg)
    finally:
        await loop.aclose()


async def test_obsolete_goal_continuation_finishes_without_starting_a_model(tmp_path):
    loop, bus, msg, coordinator = runtime(tmp_path, 'Continue the Goal', continuation=True)
    await loop.sessions.state.get(msg.session_key)
    await loop.sessions.state.update_metadata(msg.session_key, {'goal_state':{'goal_id':'old-goal', 'status':'stopped', 'objective':'Read papers'}})
    try:
        with coordinator.connected():
            await loop.dispatch.receive(msg)
            tasks = list(loop._active_tasks.get(msg.session_key, []))
            await asyncio.gather(*tasks)
        await assert_settled(bus, msg)
        loop.provider.chat_stream_with_retry.assert_not_called()
    finally:
        await loop.aclose()


async def test_pending_handoffs_share_one_completion_but_independent_owners_all_finish(tmp_path):
    from dataclasses import replace
    loop, bus, msg, coordinator = runtime(tmp_path, 'Read papers')
    queue = asyncio.Queue()
    queue.put_nowait(msg)
    queue.put_nowait(replace(msg, content='Continue', metadata={**msg.metadata, '_internal_continuation':True}))
    queue.put_nowait(replace(msg, content='A separate admitted request', metadata={**msg.metadata,
        WEBUI_TURN_METADATA_KEY:'independent-turn', WEBSOCKET_TURN_OWNER_METADATA_KEY:'independent-owner'}))
    loop._pending_queues[msg.session_key] = queue
    try:
        with coordinator.connected():
            await loop.cancel_session_work(msg.session_key, stop_goal=False)
        rows = []
        while bus.outbound_size:
            rows.append(await bus.consume_outbound())
        ended = [row.metadata[WEBUI_TURN_METADATA_KEY] for row in rows if isinstance(row.event, TurnEndEvent)]
        assert ended == ['admitted-turn', 'independent-turn']
        assert sum(isinstance(row.event, GoalStatusEvent) and row.event.status=='idle' for row in rows) == 2
    finally:
        clear_websocket_turns(msg.chat_id)
        await loop.aclose()
