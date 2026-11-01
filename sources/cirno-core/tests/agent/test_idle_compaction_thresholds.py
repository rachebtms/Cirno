import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno.agent.autocompact import AutoCompact
from cirno.memory.consolidation import Consolidator, MemoryStore
from cirno.config.loader import load_config, save_config
from cirno.config.schema import Config
from cirno.session.manager import Session, SessionManager
from cirno.utils.helpers import estimate_message_tokens
from cirno.webui.settings.api import update_runtime_config_settings


@pytest.mark.parametrize('tokens,expected', [(31_999, False), (32_000, True)])
async def test_idle_compaction_checks_size_before_emitting_events(tokens, expected):
    session = Session(key='websocket:idle')
    session.updated_at = datetime.now() - timedelta(hours=1)
    sessions = MagicMock()
    sessions.state.get_header = AsyncMock(return_value=session)
    sessions.state.get = AsyncMock(return_value=session)
    consolidator = MagicMock()
    consolidator.estimate_session_prompt_tokens.return_value = (tokens, 'test')
    consolidator.compact_idle_session = AsyncMock(return_value=None)
    bind_events = MagicMock()
    compact = AutoCompact(sessions, consolidator, 15, bind_events,
                          session_lock=defaultdict(asyncio.Lock).__getitem__,
                          min_context_tokens=32_000, keep_recent_tokens=8_000)
    await compact._archive(session.key, runtime=MagicMock())
    assert consolidator.compact_idle_session.called == expected
    assert bind_events.called == expected
    if expected:
        assert consolidator.compact_idle_session.call_args.kwargs['keep_recent_tokens'] == 8_000


async def test_retention_keeps_complete_tool_turn_and_survives_reload(tmp_path):
    sessions = SessionManager(tmp_path)
    key = 'websocket:retained'
    session = await sessions.state.get(key)
    old = [{'role': 'user', 'content': 'old ' * 100},
           {'role': 'assistant', 'content': 'old answer ' * 100}]
    recent = [
        {'role': 'user', 'content': 'Recent question'},
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'call-1', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'Recent result'},
        {'role': 'assistant', 'content': 'Recent answer'},
    ]
    session.messages = old + recent
    await sessions.state.finish_turn(session)
    consolidator = Consolidator(MemoryStore(tmp_path), sessions, lambda **kw: [], lambda: [])
    consolidator.archive_session = AsyncMock(return_value='Earlier summary')
    consolidator.estimate_session_prompt_tokens = MagicMock(return_value=(500, 'test'))
    budget = sum(estimate_message_tokens(message) for message in recent)
    await consolidator.compact_idle_session(key, runtime=MagicMock(), keep_recent_tokens=budget)
    assert consolidator.archive_session.call_args.kwargs['archive_end'] == len(old)
    await sessions.state.discard(key)
    reloaded = await sessions.state.get(key)
    assert reloaded.get_history() == recent
    assert reloaded.metadata['_last_summary']['text'] == 'Earlier summary'
    # The retained turns alone do not cause another summary or a model call.
    consolidator.archive_session.reset_mock()
    assert await consolidator.compact_idle_session(key, runtime=MagicMock(), keep_recent_tokens=budget) == ''
    consolidator.archive_session.assert_not_called()


def test_retention_never_leaves_an_orphan_tool_result():
    messages = [{'role': 'user', 'content': 'Large input ' * 1000},
                {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call-1'}]},
                {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'small'}]
    session = Session(key='websocket:large-turn', messages=messages)
    assert Consolidator._archive_boundary(session, 20) == len(messages)
    assert Consolidator._archive_boundary(session, 0) == len(messages)


def test_threshold_settings_roundtrip(tmp_path):
    path = tmp_path / 'config.json'
    save_config(Config(), path)
    values = {'agents.defaults.idle_compact_percent': 40,
              'agents.defaults.idle_compact_keep_percent': 10}
    payload = update_runtime_config_settings(values, local_browser=True, config_path=path)
    assert all(payload['runtime_config'][key] == value for key, value in values.items())
    defaults = load_config(path).agents.defaults
    assert defaults.idle_compact_percent == 40
    assert defaults.idle_compact_keep_percent == 10
    assert payload['requires_restart']
