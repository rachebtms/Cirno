"""Shutdown drains accepted work without admitting replacement workers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.outbound_events import TurnEndEvent
from cirno_core.bus.runtime_events import RuntimeEventContext, TurnCompleted
from cirno_core.providers.generation import GenerationSettings
from cirno_core.runtime.admission import RuntimeMaintenanceError
from cirno_core.session.manager import SessionManager
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator


@pytest.fixture
async def loop(tmp_path):
    provider = MagicMock(aclose=AsyncMock())
    provider.generation = GenerationSettings()
    provider.get_default_model.return_value = 'fixture'
    sessions = SessionManager(tmp_path / 'workspace', sessions_root=tmp_path / 'sessions')
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path / 'workspace', session_manager=sessions)
    yield loop
    leftovers = [task for group in loop._active_tasks.values() for task in group]
    for task in leftovers:
        task.cancel()
    await asyncio.gather(*leftovers, return_exceptions=True)
    loop._pending_queues.clear()
    await loop.aclose()


async def test_draining_background_work_cannot_start_another_worker(loop, monkeypatch):
    existing_started, release_background, background_started, new_worker_started = (asyncio.Event() for _ in range(4))

    async def existing():
        existing_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            release_background.set()

    async def new_worker(*args):
        new_worker_started.set()
        await asyncio.Event().wait()

    async def background():
        background_started.set()
        await release_background.wait()
        try:
            await loop.dispatch.enqueue(InboundMessage(channel='websocket', sender_id='system:goal', chat_id='late', content='Continue'))
        except RuntimeMaintenanceError:
            pass

    monkeypatch.setattr(loop.dispatch, 'run_queue', new_worker)
    loop._track_active_task('websocket:existing', asyncio.create_task(existing()))
    loop.schedule_background(background())
    await asyncio.wait_for(existing_started.wait(), 1)
    await asyncio.wait_for(background_started.wait(), 1)
    await loop.aclose()
    assert not new_worker_started.is_set()
    assert not loop._active_tasks
    assert not loop._pending_queues


async def test_enqueue_waiting_for_a_control_lock_is_rejected_after_stop(loop):
    key = 'websocket:late'
    async with loop.session_intake_lock(key):
        waiting = asyncio.create_task(loop.dispatch.enqueue(InboundMessage(channel='websocket', sender_id='user', chat_id='late', content='Start')))
        await asyncio.sleep(0)
        loop.stop()
    with pytest.raises(RuntimeMaintenanceError, match='stopping'):
        await waiting
    assert key not in loop._pending_queues


async def test_stop_during_journal_write_does_not_fill_the_pending_queue(loop, monkeypatch):
    key = 'websocket:late'
    pending = asyncio.Queue()
    loop._pending_queues[key] = pending
    entered, release = asyncio.Event(), asyncio.Event()

    async def journal(key, message):
        entered.set()
        await release.wait()
        return message

    monkeypatch.setattr(loop.dispatch, 'journal', journal)
    task = asyncio.create_task(loop.dispatch.enqueue(InboundMessage(channel='websocket', sender_id='user', chat_id='late', content='Follow-up')))
    await asyncio.wait_for(entered.wait(), 1)
    loop.stop()
    release.set()
    with pytest.raises(RuntimeMaintenanceError, match='stopping'):
        await task
    assert pending.empty()


@pytest.mark.parametrize('entry', ['direct', 'receive', 'background'])
async def test_stopped_runtime_rejects_other_new_work_entries(loop, entry):
    loop.stop()
    message = InboundMessage(channel='websocket', sender_id='user', chat_id='late', content='Start')
    with pytest.raises(RuntimeMaintenanceError, match='stopping'):
        if entry == 'direct':
            await loop.process_direct('Start')
        elif entry == 'receive':
            await loop.dispatch.receive(message)
        else:
            loop.schedule_background(asyncio.sleep(0))
    assert not loop._active_tasks and not loop._background_tasks


async def test_accepted_turn_completion_survives_rejected_optional_title_work(loop):
    key = 'websocket:completed'
    session = await loop.sessions.state.get(key)
    coordinator = WebuiTurnCoordinator(loop.bus, loop.sessions, loop.schedule_background)
    loop.stop()
    await coordinator._handle_turn_completed_event(TurnCompleted(
        context=RuntimeEventContext(channel='websocket', chat_id='completed', session_key=key,
                                    session_generation=session.generation, metadata={'webui': True}),
        runtime=loop.llm_runtime(),
    ))
    message = await asyncio.wait_for(loop.bus.consume_outbound(), 1)
    assert isinstance(message.event, TurnEndEvent)
    assert message.event.outcome == 'completed'
    assert not loop._background_tasks
