"""Post-model continuation limits preserve live Goal decisions and progress."""

from types import SimpleNamespace

import pytest
from cirno_core.agent.execution.processing import TurnProcessor
from cirno_core.session.goal_state import resume_goal_state
from cirno_core.session.manager import SessionManager


@pytest.fixture
async def processor(tmp_path):
    sessions = SessionManager(tmp_path / 'workspace', sessions_root=tmp_path / 'sessions')
    key = 'websocket:research'
    await sessions.state.get(key)
    goal = {'goal_id': 'same-task', 'status': 'active', 'objective': 'Verify research',
            'recap': 'Three sources checked; inspect the last artifact', 'continuation_limit': 1}
    await sessions.state.update_metadata(key, {'goal_state': goal, '_sustained_goal_continuation_rounds': 1})
    ctx = SimpleNamespace(session_key=key, session=await sessions.state.read_header(key),
                          pending_queue=None, delivery=SimpleNamespace(continuation_pending=None))
    yield TurnProcessor(SimpleNamespace(sessions=sessions, goal_continuation_limit=0)), ctx, goal
    await sessions.state.aclose()


async def test_limit_pause_keeps_verified_progress_for_resume(processor):
    service, ctx, goal = processor
    await service._continue_goal(ctx)
    saved = (await service.agent.sessions.state.read_metadata(ctx.session_key))['metadata']['goal_state']
    assert saved['status'] == 'paused'
    assert saved['pause_reason'] == 'continuation_limit'
    assert saved['recap'] == goal['recap']
    resumed = resume_goal_state(saved)
    assert resumed['recap'] == goal['recap'] and 'pause_reason' not in resumed
    assert ctx.delivery.continuation_pending is False


@pytest.mark.parametrize('change', ['stop', 'replace', 'rounds'])
async def test_limit_pause_does_not_overwrite_a_newer_decision(processor, monkeypatch, change):
    service, ctx, goal = processor
    metadata = service.agent.sessions.state.metadata
    original = metadata.mutate_metadata
    newer_goal = {**goal, 'status': 'stopped'} if change == 'stop' else {**goal, 'goal_id': 'new-task', 'objective': 'Changed objective'}

    async def intervening_change(key, mutation, **kwargs):
        def update(current):
            if change == 'rounds':
                current['_sustained_goal_continuation_rounds'] = 0
            else:
                current['goal_state'] = newer_goal
        await original(key, update)
        return await original(key, mutation, **kwargs)

    monkeypatch.setattr(metadata, 'mutate_metadata', intervening_change)
    await service._continue_goal(ctx)
    saved = (await service.agent.sessions.state.read_metadata(ctx.session_key))['metadata']
    assert saved['goal_state'] == (goal if change == 'rounds' else newer_goal)
    assert saved['_sustained_goal_continuation_rounds'] == (0 if change == 'rounds' else 1)
