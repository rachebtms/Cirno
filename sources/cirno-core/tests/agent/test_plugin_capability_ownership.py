"""Captured plugin capabilities use tiny local packages, never native MCP clients."""

import json
from pathlib import Path

import pytest
from cirno_core.agent import plugins
from cirno_core.agent.context import ContextBuilder
from cirno_core.agent.subagents.tools import SubagentTools
from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.filesystem import ReadFileTool
from cirno_core.config.home import set_instance_path
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import ToolsConfig
from cirno_core.security.workspace_access import (
    bind_workspace_scope,
    reset_workspace_scope,
    validate_workspace_scope_payload,
)
from cirno_core.skills.loader import SkillsLoader


@pytest.fixture
def scope(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    package = workspace / 'plugins' / 'owner-plugin'
    package.mkdir(parents=True)
    (package / 'plugin.json').write_text(json.dumps({'$schema': plugins.AGENT_PLUGIN_SCHEMA, 'name': 'owner-plugin'}))
    skill = package / 'skills' / 'owner-skill'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: owner-skill\ndescription: Owned plugin\nalways: true\n---\nOWNER_PLUGIN_INSTRUCTIONS\n')
    (skill / 'reference.md').write_text('Owned reference')
    first, second = tmp_path / 'first' / 'config.json', tmp_path / 'second' / 'config.json'
    home = tmp_path / 'owned-instance' / 'home'
    set_instance_path(home.parent)
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', first)
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', True, config_path=first)
    return workspace, skill, first, second, home


def test_loader_keeps_the_configuration_selected_at_construction(scope, monkeypatch, tmp_path):
    workspace, _, first, second, home = scope
    loader = SkillsLoader(workspace, home=home, builtin_skills_dir=tmp_path / 'no-builtins')
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    assert [row['name'] for row in loader.list_skills(False)] == ['owner-skill']
    assert 'OWNER_PLUGIN_INSTRUCTIONS' in loader.load_skill('owner-skill')


def test_availability_history_belongs_to_the_loaders_home(scope, tmp_path):
    workspace, _, _, _, home = scope
    directory = home / 'skills' / 'home-skill'
    directory.mkdir(parents=True)
    (directory / 'SKILL.md').write_text('---\nname: home-skill\ndescription: Owned home\n---\n')
    loader = SkillsLoader(workspace, home=home, builtin_skills_dir=tmp_path / 'no-builtins')
    other = tmp_path / 'other-instance' / 'home'
    set_instance_path(other.parent)
    assert loader.get_skill_availability('home-skill') == (True, '')
    assert len(list((home / 'skills-history' / 'home-skill').glob('*/SKILL.md'))) == 1
    assert not (other / 'skills-history').exists()


@pytest.mark.parametrize('owner_enabled', [True, False])
async def test_file_read_capability_uses_its_tool_context_configuration(scope, monkeypatch, tmp_path, owner_enabled):
    workspace, skill, first, second, home = scope
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', owner_enabled, config_path=first)
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', not owner_enabled, config_path=second)
    tool = ReadFileTool.create(ToolContext(config=ToolsConfig(restrict_to_workspace=True),
        workspace=str(workspace), home_path=home, source_config_path=first))
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    project = tmp_path / 'project'
    project.mkdir()
    access = validate_workspace_scope_payload({'project_path': str(project), 'access_mode': 'restricted'},
        default_workspace=workspace, default_restrict_to_workspace=True)
    token = bind_workspace_scope(access)
    try:
        result = await tool.execute(path=str(skill / 'reference.md'))
    finally:
        reset_workspace_scope(token)
    assert getattr(result, 'is_error', False) is not owner_enabled
    if owner_enabled:
        assert 'Owned reference' in result


def test_isolated_prompt_uses_its_captured_plugin_configuration(scope, monkeypatch):
    workspace, _, first, second, _ = scope
    tools = SubagentTools(workspace, ToolsConfig(), NetworkConfig(), True, set(), source_config_path=first)
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    assert 'OWNER_PLUGIN_INSTRUCTIONS' in tools.prompt()


def test_context_skill_discovery_keeps_the_initial_configuration(scope, monkeypatch):
    workspace, _, _, second, _ = scope
    context = ContextBuilder(workspace)
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    assert 'OWNER_PLUGIN_INSTRUCTIONS' in context.skills.load_skill('owner-skill')


def test_explicit_context_prompt_and_configuration_stay_stable_after_global_selection_changes(scope, monkeypatch):
    workspace, _, first, second, _ = scope
    context = ContextBuilder(workspace, source_config_path=first)
    before = context.build_system_prompt(session_key='websocket:fixture')
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    after = context.build_system_prompt(session_key='websocket:fixture')
    assert 'OWNER_PLUGIN_INSTRUCTIONS' in before
    assert after == before
    assert context.skills.config_path == first
    assert context.memory.dream.source_config_path == first


def test_default_plugin_discovery_keeps_one_configuration_through_its_scan(scope, monkeypatch):
    workspace, _, first, second, _ = scope
    original = plugins._installed_plugins

    def switch_during_scan(workspace):
        result = original(workspace)
        monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
        return result

    monkeypatch.setattr(plugins, '_installed_plugins', switch_during_scan)
    assert [skill.name for skill in plugins.enabled_agent_plugin_skill_documents(workspace)] == ['owner-skill']


@pytest.mark.parametrize('change', ['remove', 'invalid-utf8', 'replace'])
def test_external_marker_removal_revokes_a_cached_read_capability(scope, change):
    workspace, skill, first, _, _ = scope
    assert plugins.enabled_agent_plugin_skill_dirs(workspace, config_path=first) == (skill,)
    markers = list((first.parent / 'state' / 'plugin-data').glob('*/owner-plugin/enabled'))
    assert len(markers) == 1
    if change == 'remove':
        markers[0].unlink()
    elif change == 'invalid-utf8':
        markers[0].write_bytes(b'\xff')
    else:
        markers[0].write_text('revoked outside this process')
    assert plugins.enabled_agent_plugin_skill_dirs(workspace, requested_path=skill / 'reference.md', config_path=first) == ()


def test_v1_fingerprint_activation_requires_explicit_reenable(scope):
    from hashlib import sha256
    workspace, skill, first, _, _ = scope
    package = skill.parent.parent
    digest = sha256()
    for entry in sorted(package.rglob('*')):
        digest.update(entry.relative_to(package).as_posix().encode())
        digest.update(b'\0dir\0' if entry.is_dir() else b'\0file\0' + entry.read_bytes())
        digest.update(b'\0')
    marker = next((first.parent / 'state' / 'plugin-data').glob('*/owner-plugin/enabled'))
    marker.write_text(json.dumps({'fingerprint': digest.hexdigest(), 'root': str(package)}, separators=(',', ':'), sort_keys=True))
    assert plugins.discover_agent_plugins(workspace, config_path=first)[0].enabled is False
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', True, config_path=first)
    assert plugins.discover_agent_plugins(workspace, config_path=first)[0].enabled is True


def test_invalid_utf8_activation_is_unavailable_without_breaking_discovery(scope):
    workspace, _, first, _, _ = scope
    marker = next((first.parent / 'state' / 'plugin-data').glob('*/owner-plugin/enabled'))
    marker.write_bytes(b'\xff\xfe')
    assert plugins.discover_agent_plugins(workspace, config_path=first)[0].enabled is False
    assert plugins.enabled_agent_plugin_skill_documents(workspace, config_path=first) == []


def test_plugin_activation_distinguishes_content_from_file_tree_boundaries(scope):
    workspace, skill, first, _, _ = scope
    package = skill.parent.parent
    first_file = package / 'a'
    first_file.write_bytes(b'x\x00b\x00file\x00y')
    fingerprint = plugins._package_fingerprint(package)
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', True, config_path=first)
    first_file.write_bytes(b'x')
    (package / 'b').write_bytes(b'y')
    assert plugins.discover_agent_plugins(workspace, config_path=first)[0].enabled is False
    assert plugins._package_fingerprint(package) != fingerprint


def test_reading_plugin_state_during_enable_never_observes_a_partial_marker(scope, monkeypatch):
    import builtins
    import io
    workspace, _, first, _, _ = scope
    marker = next((first.parent / 'state' / 'plugin-data').glob('*/owner-plugin/enabled'))
    observed = []

    def inspect_open(delegate):
        def open_file(file, mode='r', *args, **kwargs):
            stream = delegate(file, mode, *args, **kwargs)
            if isinstance(file, (str, Path)) and Path(file).parent == marker.parent and any(flag in mode for flag in ('w', 'x')):
                observed.append(plugins.discover_agent_plugins(workspace, config_path=first)[0].enabled)
            return stream
        return open_file

    monkeypatch.setattr(builtins, 'open', inspect_open(builtins.open))
    monkeypatch.setattr(io, 'open', inspect_open(io.open))
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', True, config_path=first)
    assert observed == [True]
    assert plugins.discover_agent_plugins(workspace, config_path=first)[0].enabled is True


def test_cached_activation_state_cannot_follow_a_retargeted_data_directory(scope, tmp_path, create_symlink):
    workspace, skill, first, _, _ = scope
    assert plugins.enabled_agent_plugin_skill_dirs(workspace, config_path=first) == (skill,)
    directory = first.parent / 'state' / 'plugin-data'
    outside = tmp_path / 'outside-data'
    directory.rename(outside)
    create_symlink(directory, outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match='escapes its parent'):
        plugins.enabled_agent_plugin_skill_dirs(workspace, requested_path=skill / 'reference.md', config_path=first)


def test_cached_read_roots_cannot_follow_a_retargeted_package_directory(scope, tmp_path, create_symlink):
    workspace, skill, first, _, _ = scope
    assert plugins.enabled_agent_plugin_skill_dirs(workspace, config_path=first) == (skill,)
    package = skill.parent.parent
    outside = tmp_path / 'outside-package'
    package.rename(outside)
    create_symlink(package, outside, target_is_directory=True)
    assert plugins.enabled_agent_plugin_skill_dirs(workspace, config_path=first) == ()
