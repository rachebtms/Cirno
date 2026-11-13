"""Owner-selected Skills and memory documents preserve role and cache boundaries."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from cirno_core.agent.context import ContextBuilder, TranscriptInput
from cirno_core.config.home import get_home_path
from cirno_core.memory.context_files import memory_files_context
from cirno_core.runtime.context import RUNTIME_CONTEXT_HISTORY_META, RUNTIME_CONTEXT_MESSAGE_META
from cirno_core.skills.loader import SkillsLoader
from cirno_memory.config import MemoryConfig
from sources.development.testing.skills import write_skill


def test_fixed_skills_reuse_availability_and_disabled_rules(tmp_path):
    root = get_home_path() / 'skills'
    write_skill(root, 'chosen', body='Use the owner-selected procedure.')
    write_skill(root, 'disabled')
    write_skill(root, 'missing', metadata_json={'requires': {'bins': ['cirno_missing_test_binary_0214']}})
    write_skill(root, 'declared', metadata_json={'always': True})
    loader = SkillsLoader(tmp_path, builtin_skills_dir=tmp_path/'empty', always_skills={'chosen','disabled','missing'}, disabled_skills={'disabled'})
    assert loader.get_always_skills() == ['chosen', 'declared']
    builder = ContextBuilder(tmp_path, always_skills=['chosen','chosen'])
    prompt = builder.build_system_prompt(session_key='websocket:worker')
    assert prompt.count('Use the owner-selected procedure.') == 1


def test_fixed_memory_changes_append_to_fresh_input_without_rewriting_history(tmp_path):
    home = get_home_path()
    memory = home / 'memory'
    memory.mkdir(parents=True)
    (memory/'MEMORY.md').write_text('Shared overview')
    selected = memory/'rules.md'
    selected.write_text('Owner-selected rules version A')
    builder = ContextBuilder(tmp_path)
    builder.memory_context_files = ['memory/rules.md']
    first = builder.build_transcript(TranscriptInput(history=[], current_message='hello'), session_key='websocket:worker')
    assert 'Owner-selected rules version A' in first[-1]['content']
    persisted = {'role':'user','content':first[-1]['content'],RUNTIME_CONTEXT_HISTORY_META:first[-1]['_meta'][RUNTIME_CONTEXT_MESSAGE_META]}
    original = deepcopy(persisted)
    assert builder.build_memory_context([persisted]) is None
    selected.write_text('Owner-selected rules version B')
    second = builder.build_messages([persisted], 'continue', session_key='websocket:worker')
    assert second[0] == first[0]
    assert persisted == original
    assert 'Owner-selected rules version B' in second[-1]['content']
    builder.memory_context_files = []
    cleared = builder.build_memory_context([persisted])
    assert cleared is not None and 'Owner-selected rules' not in cleared.content


def test_fixed_memory_file_budget_and_missing_file_are_explicit(tmp_path):
    (tmp_path/'memory').mkdir()
    for name in ('a','b'):
        (tmp_path/'memory'/f'{name}.md').write_text(name * 100_000)
    content = memory_files_context(tmp_path, ['memory/a.md','memory/b.md'], 256)
    assert 'memory/a.md' in content and 'memory/b.md' in content
    assert len(content) < 3000
    with pytest.raises(FileNotFoundError):
        memory_files_context(tmp_path, ['memory/missing.md'], 256)
    secret = tmp_path/'secret.txt'
    secret.write_text('private')
    (tmp_path/'memory'/'escape.md').symlink_to(secret)
    with pytest.raises(ValueError, match='escapes'):
        memory_files_context(tmp_path, ['memory/escape.md'], 256)


def test_fixed_memory_paths_are_home_relative_and_deduplicated():
    config = MemoryConfig(context_files=['memory/rules.md','memory/rules.md','memory/MEMORY.md'])
    assert config.context_files == ['memory/rules.md']
    for path in ('../secret','/etc/passwd','SOUL.md','memory/../../secret','C:\\secret'):
        with pytest.raises(ValidationError):
            MemoryConfig(context_files=[path])


def test_selected_skills_reload_before_building_the_next_prompt(tmp_path):
    from unittest.mock import MagicMock
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.config.loader import save_config, load_config
    from cirno_core.config.schema import Config
    from cirno_core.providers.base import LLMProvider
    from cirno_core.agent.tools.registry import ToolRegistry
    root = get_home_path() / 'skills'
    write_skill(root, 'chosen', body='Selected procedure body')
    path = tmp_path/'config.json'
    config = Config()
    config.agents.defaults.workspace = str(tmp_path/"workspace")
    save_config(config,path)
    loop = AgentLoop.from_config(load_config(path), provider=MagicMock(spec=LLMProvider), model='test', tool_registry=ToolRegistry())
    config.agents.defaults.always_skills = ['chosen']
    save_config(config,path)
    assert 'Selected procedure body' in loop.context.build_system_prompt(session_key='websocket:worker')
    assert 'Selected procedure body' in loop.subagents.tools.prompt()
    config.agents.defaults.always_skills = []
    save_config(config,path)
    assert 'Selected procedure body' not in loop.subagents.tools.prompt()
    assert 'Selected procedure body' not in loop.context.build_system_prompt(session_key='websocket:worker')


def test_selected_memory_reloads_before_prompt_preparation(tmp_path):
    from unittest.mock import MagicMock
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.config.loader import save_config, load_config
    from cirno_core.config.schema import Config
    from cirno_core.providers.base import LLMProvider

    home = get_home_path()
    (home / "memory").mkdir(parents=True, exist_ok=True)
    (home / "memory/rules.md").write_text("Fresh selected memory")
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    save_config(config, path)
    loop = AgentLoop.from_config(load_config(path), provider=MagicMock(spec=LLMProvider), model="test", tool_registry=ToolRegistry())
    config.agents.defaults.memory.context_files = ["memory/rules.md"]
    save_config(config, path)
    # Actual turn preparation assembles memory before capturing the system prompt.
    block = loop.context.build_memory_context([])
    assert block is not None and "Fresh selected memory" in block.content
    config.agents.defaults.memory.context_files = []
    save_config(config, path)
    assert loop.context.build_memory_context([]) is None
