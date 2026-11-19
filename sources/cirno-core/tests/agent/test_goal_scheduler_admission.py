"""Goal wake decisions use the metadata at their commit boundary."""

from datetime import datetime, timedelta, timezone
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.goals.scheduler import _wake_goal
from cirno_core.agent.goals.scheduler import wake_due_goals
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import RECOVERY_METADATA_KEY
from cirno_core.runtime.admission import RuntimeMaintenanceError


@pytest.fixture
async def waiting_goal(tmp_path):
    sessions = SessionManager(tmp_path / 'workspace', sessions_root=tmp_path / 'sessions')
    key = 'websocket:research'
    await sessions.state.get(key)
    goal = {'goal_id': 'same-task', 'status': 'waiting', 'objective': 'Verify research',
            'recap': 'Three sources already checked', 'continuation_limit': 0,
            'wake_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
    await sessions.state.update_metadata(key, {'goal_state': goal, '_sustained_goal_continuation_rounds': 1})
    loop = SimpleNamespace(sessions=sessions, _pending_queues={}, _discarding_sessions=set(),
                           goal_continuation_limit=0, dispatch=SimpleNamespace(enqueue=AsyncMock()))
    yield loop, key, goal
    await sessions.state.aclose()


@pytest.mark.parametrize('limit', [0, 1])
@pytest.mark.parametrize('late_state', [
    {'runtime_checkpoint': {'phase': 'tools_completed'}},
    {'pending_user_turn': {'message_id': 'new-user-input'}},
    {RECOVERY_METADATA_KEY: {'status': 'awaiting_user', 'recovery_id': 'new-interruption'}},
])
async def test_new_recovery_state_blocks_a_stale_wake_decision(waiting_goal, monkeypatch, limit, late_state):
    loop, key, goal = waiting_goal
    goal = {**goal, 'continuation_limit': limit}
    await loop.sessions.state.update_metadata(key, {'goal_state': goal})
    original = loop.sessions.state.mutate_metadata

    async def concurrent_change(key, change, **kwargs):
        await original(key, lambda current: current.update(late_state))
        return await original(key, change, **kwargs)

    monkeypatch.setattr(loop.sessions.state, 'mutate_metadata', concurrent_change)
    await _wake_goal(loop, key, datetime.now(timezone.utc))
    loop.dispatch.enqueue.assert_not_awaited()
    current = (await loop.sessions.state.read_metadata(key))['metadata']
    assert current['goal_state'] == goal
    assert current['_sustained_goal_continuation_rounds'] == 1


@pytest.mark.parametrize('limit', [0, 5])
async def test_wake_uses_the_latest_continuation_count(waiting_goal, monkeypatch, limit):
    loop, key, goal = waiting_goal
    await loop.sessions.state.update_metadata(key, {'goal_state': {**goal, 'continuation_limit': limit}})
    original = loop.sessions.state.mutate_metadata

    async def concurrent_change(key, change, **kwargs):
        await original(key, lambda current: current.update(_sustained_goal_continuation_rounds=5))
        return await original(key, change, **kwargs)

    monkeypatch.setattr(loop.sessions.state, 'mutate_metadata', concurrent_change)
    await _wake_goal(loop, key, datetime.now(timezone.utc))
    current = (await loop.sessions.state.read_metadata(key))['metadata']
    assert current['_sustained_goal_continuation_rounds'] == (5 if limit else 6)
    if limit:
        loop.dispatch.enqueue.assert_not_awaited()
        assert current['goal_state']['status'] == 'paused'
    else:
        loop.dispatch.enqueue.assert_awaited_once()
    assert current['goal_state']['recap'] == goal['recap']


@pytest.mark.parametrize('error', [RuntimeMaintenanceError, asyncio.CancelledError])
async def test_rejected_admission_does_not_consume_a_goal_round(waiting_goal, error):
    loop, key, goal = waiting_goal
    loop.dispatch.enqueue.side_effect = error('not admitted')
    with pytest.raises(error):
        await _wake_goal(loop, key, datetime.now(timezone.utc))
    current = (await loop.sessions.state.read_metadata(key))['metadata']
    assert current['goal_state'] == goal
    assert current['_sustained_goal_continuation_rounds'] == 1


async def test_cancellation_after_reservation_commit_restores_the_wait(waiting_goal, monkeypatch):
    loop, key, goal = waiting_goal
    original = loop.sessions.state.mutate_metadata
    committed = asyncio.Event()
    intercept = True

    async def pause_after_commit(key, change, **kwargs):
        nonlocal intercept
        result = await original(key, change, **kwargs)
        if intercept:
            intercept = False
            committed.set()
            await asyncio.Event().wait()
        return result

    monkeypatch.setattr(loop.sessions.state, 'mutate_metadata', pause_after_commit)
    task = asyncio.create_task(_wake_goal(loop, key, datetime.now(timezone.utc)))
    await asyncio.wait_for(committed.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    current = (await loop.sessions.state.read_metadata(key))['metadata']
    assert current['goal_state'] == goal
    assert current['_sustained_goal_continuation_rounds'] == 1


@pytest.mark.parametrize('newer', ['stop', 'admitted'])
async def test_reservation_rollback_keeps_newer_controls_and_accepted_work(waiting_goal, newer):
    loop, key, goal = waiting_goal

    async def enqueue(message):
        if newer == 'stop':
            await loop.sessions.state.update_metadata(key, {'goal_state': {**goal, 'status': 'stopped', 'recap': 'Owner stopped the task'}})
        else:
            loop._pending_queues[key] = asyncio.Queue()
        raise RuntimeMaintenanceError('new work admission failed')

    loop.dispatch.enqueue.side_effect = enqueue
    with pytest.raises(RuntimeMaintenanceError):
        await _wake_goal(loop, key, datetime.now(timezone.utc))
    current = (await loop.sessions.state.read_metadata(key))['metadata']
    assert current['goal_state']['status'] == ('stopped' if newer == 'stop' else 'active')
    assert current['_sustained_goal_continuation_rounds'] == 2
    if newer == 'stop':
        assert current['goal_state']['recap'] == 'Owner stopped the task'


async def test_closed_admission_is_not_reported_as_a_scheduler_fault(waiting_goal, monkeypatch):
    loop, key, goal = waiting_goal
    loop.dispatch.enqueue.side_effect = RuntimeMaintenanceError('stopping')
    monkeypatch.setattr('cirno_core.agent.goals.scheduler.report_service_error', lambda *args, **kwargs: pytest.fail('Shutdown produced a scheduler error notification'))
    await wake_due_goals(loop)
    current = (await loop.sessions.state.read_metadata(key))['metadata']
    assert current['goal_state'] == goal
    assert current['_sustained_goal_continuation_rounds'] == 1
