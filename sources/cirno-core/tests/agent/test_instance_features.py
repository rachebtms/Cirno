"""Integration contracts for durable Goals, projects, evidence and SSH Nodes."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno.agent.goals.permission import goal_mutation_permission
from cirno.agent.tools.context import RequestContext, request_context
from cirno.agent.tools.long_task import CreateGoalTool, UpdateGoalTool
from cirno.agent.tools.coordination import CreateSessionTool
from cirno.agent.tools.instance_features import MemoryTool
from cirno.agent.goals.scheduler import wake_due_goals
from cirno.bus.queue import MessageBus
from cirno.config.home import set_home_path
from cirno.config.schema import Config
from cirno.storage.instance import InstanceData
from cirno.nodes.service import Nodes
from cirno.session.manager import SessionManager
from cirno.session.turn_continuation import clear_internal_continuation_state, _goal_continuation_available
from cirno.skills.history import snapshot_skill, skill_versions
from cirno.webui.instance_api import instance_action


@pytest.fixture
def home(tmp_path):
    path = tmp_path / 'home'
    set_home_path(path)
    yield path
    set_home_path(None)


@pytest.fixture
async def sessions(home):
    manager = SessionManager(home / 'workspace', sessions_root=home / 'sessions')
    await manager.state.get('websocket:one')
    await manager.state.update_metadata('websocket:one', {'title': 'One'})
    yield manager
    await manager.state.aclose()


def context(key='websocket:one'):
    channel, chat_id = key.split(':', 1)
    return request_context(RequestContext(channel=channel, chat_id=chat_id, session_key=key, turn_id='turn-1', message_id='message-1'))


async def control(sessions, action, **values):
    with context(), goal_mutation_permission(True):
        return await UpdateGoalTool(sessions).execute(action=action, **values)


async def test_goal_controls_keep_counters_wait_and_replace_identity(sessions):
    with context(), goal_mutation_permission(True):
        await CreateGoalTool(sessions, continuation_limit=7).execute(objective='Produce a verified file')
    first = (await sessions.state.read_metadata('websocket:one'))['metadata']['goal_state']
    assert first['continuation_limit'] == 7
    await sessions.state.update_metadata('websocket:one', {'_sustained_goal_continuation_rounds': 3})
    await control(sessions, 'wait', wake_after_seconds=3600, recap='Waiting for an external result')
    metadata = (await sessions.state.read_metadata('websocket:one'))['metadata']
    assert metadata['goal_state']['status'] == 'waiting'
    assert datetime.fromisoformat(metadata['goal_state']['wake_at']) > datetime.now(timezone.utc)
    clear_internal_continuation_state(metadata)
    assert metadata['_sustained_goal_continuation_rounds'] == 3
    await control(sessions, 'resume')
    await control(sessions, 'stop')
    assert (await sessions.state.read_metadata('websocket:one'))['metadata']['goal_state']['status'] == 'stopped'
    await control(sessions, 'resume', continuation_limit=0)
    await control(sessions, 'replace', objective='A new objective')
    metadata = (await sessions.state.read_metadata('websocket:one'))['metadata']
    assert metadata['goal_state']['goal_id'] != first['goal_id']
    assert metadata['goal_state']['continuation_limit'] == 0
    assert metadata.get('_sustained_goal_continuation_rounds', 0) == 0
    with context(), goal_mutation_permission(False):
        result = await UpdateGoalTool(sessions).execute(action='complete', recap='Result verified')
    assert not getattr(result, 'is_error', False)
    assert (await sessions.state.read_metadata('websocket:one'))['metadata']['goal_state']['status'] == 'completed'
    await control(sessions, 'delete')
    assert 'goal_state' not in (await sessions.state.read_metadata('websocket:one'))['metadata']


@pytest.mark.parametrize("serialized", [False, True])
async def test_goal_wait_wakes_from_storage_and_stopped_goal_stays_stopped(sessions, serialized):
    await sessions.state.update_metadata('websocket:one', {'goal_state': {'goal_id': 'stable', 'status': 'waiting', 'objective': 'Check external work', 'wake_at': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), 'continuation_limit': 0}, '_sustained_goal_continuation_rounds': 50})
    if serialized:
        current = (await sessions.state.read_metadata('websocket:one'))['metadata']['goal_state']
        await sessions.state.update_metadata('websocket:one', {'goal_state': json.dumps(current)})
    # Discarding the cache simulates a fresh process reading persisted state.
    await sessions.state.discard('websocket:one')
    loop = SimpleNamespace(sessions=sessions, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0, _enqueue_session_message=AsyncMock())
    await wake_due_goals(loop)
    queued = loop._enqueue_session_message.await_args.args[0]
    assert queued.metadata['_goal_id'] == 'stable'
    assert queued.session_key == 'websocket:one'
    metadata = (await sessions.state.read_metadata('websocket:one'))['metadata']
    assert metadata['_sustained_goal_continuation_rounds'] == 51
    assert _goal_continuation_available(metadata)
    await control(sessions, 'stop')
    loop._enqueue_session_message.reset_mock()
    await wake_due_goals(loop)
    loop._enqueue_session_message.assert_not_awaited()


async def test_goal_limit_pauses_without_resetting_count(sessions):
    await sessions.state.update_metadata('websocket:one', {'goal_state': {'status': 'active', 'objective': 'Bounded work', 'continuation_limit': 2}, '_sustained_goal_continuation_rounds': 2})
    loop = SimpleNamespace(sessions=sessions, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0, _enqueue_session_message=AsyncMock())
    await wake_due_goals(loop)
    metadata = (await sessions.state.read_metadata('websocket:one'))['metadata']
    assert metadata['goal_state']['status'] == 'paused'
    assert metadata['_sustained_goal_continuation_rounds'] == 2
    loop._enqueue_session_message.assert_not_awaited()


async def test_project_identity_independent_of_directory_and_delete_preserves_sessions(sessions, home):
    async def api(action, **values):
        return await instance_action({'action': action, 'values': values}, sessions=sessions, bus=MessageBus())
    a = (await api('projects.save', name='A', working_directory='/same'))['project']
    b = (await api('projects.save', name='B', working_directory='/same'))['project']
    assert a['id'] != b['id']
    await api('projects.assign', session_key='websocket:one', project_id=a['id'])
    await api('projects.delete', id=a['id'])
    metadata = (await sessions.state.read_metadata('websocket:one'))['metadata']
    assert metadata['project_id'] is None
    assert metadata['title'] == 'One'
    assert InstanceData().get('projects', b['id'])['name'] == 'B'
    result = await api('bootstrap')
    assert result['global_session_key'] == 'websocket:global'
    with pytest.raises(ValueError, match='global'):
        await api('projects.assign', session_key='websocket:global', project_id=b['id'])


async def test_ordinary_session_delegates_goal_and_reply_returns_to_owner(sessions):
    with context():
        delegated = json.loads(await CreateSessionTool(sessions).execute(title='Review', objective='Review output and report'))
    target = delegated['session_key']
    await sessions.state.update_metadata(target, {'goal_state': {**delegated['goal'], 'status': 'completed', 'recap': 'Verified'}})
    sender = SimpleNamespace(enqueue=AsyncMock())
    loop = SimpleNamespace(sessions=sessions, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0, tools=SimpleNamespace(get=lambda name: sender), _enqueue_session_message=AsyncMock())
    await wake_due_goals(loop)
    assert sender.enqueue.await_args.kwargs['source_session_key'] == target
    assert sender.enqueue.await_args.kwargs['target_handle'].startswith('@')
    assert 'Verified' in sender.enqueue.await_args.kwargs['content']
    await wake_due_goals(loop)
    assert sender.enqueue.await_count == 1


async def test_memory_keeps_sources_and_scopes_in_home(sessions, home):
    tool = MemoryTool(sessions)
    with context():
        saved = json.loads(await tool.execute(action='save', content='观察：中文检索可用', source='https://example.org/evidence#2', scope='session'))
        record = json.loads(await tool.execute(action='read', memory_id=saved['id']))
        assert '中文检索' in record['content']
        assert record['message_id'] == 'message-1'
        assert record['turn_id'] == 'turn-1'
        assert (home / 'memory/entries' / (saved['id']+'.md')).exists()
        assert json.loads(await tool.execute(action='search', query='中文', purpose='evidence'))['memories'][0]['id'] == saved['id']
    await sessions.state.get('websocket:two')
    await sessions.state.update_metadata('websocket:two', {'title':'Two'})
    with context('websocket:two'):
        assert json.loads(await tool.execute(action='search', query='中文', purpose='evidence'))['memories'] == []


async def test_memory_tool_defaults_to_knowledge_and_restricts_dream_confirmation(sessions, home):
    from cirno.memory.repository import MemoryRepository
    tool = MemoryTool(sessions)
    with context():
        event = json.loads(await tool.execute(action='save', content='Historical widget setting', source='test:user', tags=['widget'], observed_at='2024-02-29T12:00:00Z'))
        assert json.loads(await tool.execute(action='search', query='widget'))['memories'] == []
        assert json.loads(await tool.execute(action='search', query='widget', purpose='evidence', since='2024-02-29', until='2024-02-29'))['memories'][0]['id'] == event['id']
        assert json.loads(await tool.execute(action='tags'))['tags'] == [{'name': 'widget', 'count': 1}]
        denied = await tool.execute(action='confirm', memory_id=event['id'], input_revision=1, outcome='skipped', reason='Ordinary execution cannot settle Dream')
        assert getattr(denied, 'is_error', False)
    repo = MemoryRepository(home)
    token, _ = repo.pending()
    dream = MemoryTool(sessions, maintenance=True, owner_access=dict(session_key='websocket:one', project_id=None, maintenance=False), evidence_ids={event['id']}, batch_token=token)
    with context():
        knowledge = json.loads(await dream.execute(action='save', layer='knowledge', based_on=event['id'], content='Widget setting from recorded evidence', source=f"memory:{event['id']}"))
        confirmed = json.loads(await dream.execute(action='confirm', memory_id=event['id'], input_revision=1, outcome='created', target_ids=[knowledge['id']], reason='Grounded setting saved'))
        assert confirmed['outcome'] == 'created'
    assert repo.finish(token)['retained'] == 0


def test_skill_history_preserves_versions_without_rollback(home):
    directory = home / 'skills' / 'example'
    directory.mkdir(parents=True)
    (directory / 'SKILL.md').write_text('---\nname: example\ndescription: Example skill\n---\nOriginal instructions\n')
    script = directory / 'run.py'
    script.write_text('print("first")\n')
    first = snapshot_skill(directory, home)
    script.write_text('def broken(:\n')
    second = snapshot_skill(directory, home)
    assert first['valid'] and not second['valid']
    assert first['revision'] != second['revision']
    assert len(skill_versions('example', home)) == 2
    assert script.read_text() == 'def broken(:\n'
    from pathlib import Path
    assert (Path(first['path'])/'run.py').read_text() == 'print("first")\n'


def test_percent_threshold_validation_and_model_inheritance():
    config = Config.model_validate({'agents': {'defaults': {'idleCompactPercent': 30, 'idleCompactKeepPercent': 5}}, 'modelPresets': {'small': {'model': 'test', 'contextWindowTokens': 10000, 'idleCompactPercent': 20, 'idleCompactKeepPercent': 3}}})
    assert config.resolve_preset('small').idle_compact_percent == 20
    assert config.resolve_default_preset().idle_compact_percent == 30
    with pytest.raises(ValueError, match='retention'):
        Config.model_validate({'agents': {'defaults': {'idleCompactPercent': 10, 'idleCompactKeepPercent': 20}}})


async def test_node_output_is_bounded_and_ssh_failure_is_visible(home):
    import sys
    nodes = Nodes(InstanceData(home))
    out = await nodes._run([sys.executable, '-c', 'import sys; sys.stdout.write("x"*3000000)'])
    assert len(out) == 64000
    with pytest.raises(RuntimeError, match='specific failure'):
        await nodes._run([sys.executable, '-c', 'import sys; sys.stderr.write("specific failure"); sys.exit(4)'])
    with pytest.raises(TimeoutError):
        await nodes._run([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=0.05)


async def test_stop_cancels_the_live_goal_and_scheduler_does_not_restart_it(home):
    from unittest.mock import MagicMock
    from cirno.agent.loop import AgentLoop
    from cirno.bus.events import InboundMessage
    from cirno.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
    from agent.session_helpers import stop_loop

    waiting = asyncio.Event()
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = 'test-model'
    provider.generation = GenerationSettings()
    provider.estimate_prompt_tokens.return_value = (100, 'test')
    calls = 0
    async def respond(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(content=None, tool_calls=[ToolCallRequest(id='create', name='create_goal', arguments={'objective':'Work until explicitly stopped'})])
        waiting.set()
        await asyncio.Event().wait()
    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=home/'workspace', model='test-model')
    run = asyncio.create_task(loop.run())
    try:
        await loop.bus.publish_inbound(InboundMessage(channel='websocket',sender_id='user',chat_id='stop-check',content='Continue working with a Goal.'))
        await asyncio.wait_for(waiting.wait(), 5)
        await loop.discard_session('websocket:stop-check')
        goal=(await loop.sessions.state.read_metadata('websocket:stop-check'))['metadata']['goal_state']
        assert goal['status'] == 'stopped'
        await wake_due_goals(loop)
        assert calls == 2
        assert 'websocket:stop-check' not in loop._pending_queues
    finally:
        await stop_loop(loop, run, timeout=5)


async def test_wait_and_round_count_survive_a_new_storage_owner(home):
    path=home/'sessions'
    first=SessionManager(home/'workspace',sessions_root=path)
    key='websocket:restart-wait'
    await first.state.get(key)
    await first.state.update_metadata(key, {'goal_state':{'goal_id':'wait-id','objective':'Wake once','status':'waiting','continuation_limit':0,'wake_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()},'_sustained_goal_continuation_rounds':4})
    await first.state.aclose()
    second=SessionManager(home/'workspace',sessions_root=path)
    loop=SimpleNamespace(sessions=second,_pending_queues={},_discarding_sessions=set(),goal_continuation_limit=0,_enqueue_session_message=AsyncMock())
    try:
        await wake_due_goals(loop)
        assert loop._enqueue_session_message.await_args.args[0].metadata['_goal_id']=='wait-id'
        assert (await second.state.read_metadata(key))['metadata']['_sustained_goal_continuation_rounds']==5
    finally:
        await second.state.aclose()


async def test_model_percentage_uses_each_model_window_and_skips_short_context(sessions):
    from cirno.agent.autocompact import AutoCompact
    runtime=SimpleNamespace(context_window_tokens=10000,idle_compact_percent=20,idle_compact_keep_percent=5)
    key='websocket:one'
    consolidator=SimpleNamespace(estimate_session_prompt_tokens=lambda *args,**kwargs:(1000,'test'),compact_idle_session=AsyncMock(return_value='Summary'))
    compact=AutoCompact(sessions=sessions,consolidator=consolidator,session_ttl_minutes=15,session_lock=lambda key:asyncio.Lock(),trigger_percent=30,keep_percent=3)
    compact._is_expired = lambda *args, **kwargs: True
    await compact._archive(key,runtime=runtime)
    consolidator.compact_idle_session.assert_not_awaited()
    consolidator.estimate_session_prompt_tokens=lambda *args,**kwargs:(3000,'test')
    await compact._archive(key,runtime=runtime)
    assert consolidator.compact_idle_session.await_args.kwargs['keep_recent_tokens']==500
    runtime.idle_compact_percent=0
    consolidator.compact_idle_session.reset_mock()
    await compact._archive(key,runtime=runtime)
    consolidator.compact_idle_session.assert_not_awaited()


async def test_dream_cannot_mix_project_evidence_or_update_shared_memory(sessions, home):
    from cirno.memory.repository import MemoryRepository
    repo = MemoryRepository(home)
    own = repo.save('project A fact', source='test:a', session_key='websocket:one', project_id='p1', scope='project')
    other = repo.save('project B fact', source='test:b', session_key='websocket:two', project_id='p2', scope='project')
    shared = repo.save('shared preference', source='test:user', session_key='user', scope='user', layer='knowledge')
    tool = MemoryTool(maintenance=True, owner_access=dict(session_key='websocket:one', project_id='p1', maintenance=False), evidence_ids={own['id']})
    with context('dream:batch'):
        assert getattr(await tool.execute(action='read', memory_id=other['id']), 'is_error', False)
        assert getattr(await tool.execute(action='save', content='new', source='memory:'+other['id'], based_on=other['id'], layer='knowledge'), 'is_error', False)
        assert getattr(await tool.execute(action='update', memory_id=shared['id'], expected_revision=1, content='project fact', source='memory:'+own['id'], based_on=own['id']), 'is_error', False)
        derived = json.loads(await tool.execute(action='save', content='derived fact', source='memory:'+own['id'], based_on=own['id'], layer='knowledge'))
    assert derived['scope'] == 'project' and derived['project_id'] == 'p1'
