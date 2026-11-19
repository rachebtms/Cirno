"""File tools preserve the Home belonging to their captured capability context."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_core.agent.tools.filesystem import WriteFileTool
from cirno_core.config.home import set_instance_path
from cirno_core.config.tools import ToolsConfig
from cirno_core.skills.history import skill_versions


@pytest.mark.parametrize('changed_at', ['before-create', 'before-execute'])
async def test_file_tool_context_home_owns_write_capabilities_and_both_history_snapshots(tmp_path, changed_at):
    owned, other = tmp_path / 'owned' / 'home', tmp_path / 'other' / 'home'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    target = owned / 'skills' / 'owned-fixture' / 'SKILL.md'
    target.parent.mkdir(parents=True)
    initial = '---\nname: owned-fixture\ndescription: Before\n---\n'
    updated = '---\nname: owned-fixture\ndescription: After\n---\n'
    target.write_text(initial)
    set_instance_path(owned.parent)
    context = SimpleNamespace(workspace=str(workspace), home_path=owned, file_state_store=None,
        source_config_path=None, instance_config_path=tmp_path / 'owned' / 'config.json',
        config=ToolsConfig(restrict_to_workspace=True))
    if changed_at == 'before-create':
        set_instance_path(other.parent)
    tool = WriteFileTool.create(context)
    set_instance_path(other.parent)
    result = await tool.execute(path=str(target), content=updated)
    assert not getattr(result, 'is_error', False), result
    assert target.read_text() == updated
    versions = skill_versions('owned-fixture', owned)
    assert len(versions) == 2
    assert {Path(item['path']).joinpath('SKILL.md').read_text() for item in versions} == {initial, updated}
    assert not (other / 'skills-history').exists()


async def test_a_constructed_file_tool_does_not_gain_another_instances_home_write_capability(tmp_path):
    owned, other = tmp_path / 'owned' / 'home', tmp_path / 'other' / 'home'
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    target = other / 'skills' / 'other-fixture' / 'SKILL.md'
    target.parent.mkdir(parents=True)
    target.write_text('other owner')
    set_instance_path(owned.parent)
    context = SimpleNamespace(workspace=str(workspace), home_path=owned, file_state_store=None,
        source_config_path=None, instance_config_path=tmp_path / 'owned' / 'config.json',
        config=ToolsConfig(restrict_to_workspace=True))
    set_instance_path(other.parent)
    tool = WriteFileTool.create(context)
    result = await tool.execute(path=str(target), content='must not replace')
    assert getattr(result, 'is_error', False), result
    assert target.read_text() == 'other owner'
