"""Managed CLI Skills retain valid YAML identity without rewriting their body."""

import pytest
from cirno_core.apps.cli.paths import cli_app_skill_path
from cirno_core.apps.cli.service import CliAppManager
from cirno_core.skills.metadata import parse_skill_metadata, valid_skill_metadata
from cirno_core.skills.validation import validate_skill


@pytest.mark.parametrize('name', ['a' * 64, 'research__tools', 'research--tools'])
def test_valid_registry_names_generate_loadable_skills(tmp_path, monkeypatch, name):
    monkeypatch.setattr('cirno_core.apps.cli.paths.get_home_path', lambda: tmp_path)
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    monkeypatch.setattr(manager, '_fetch_skill_content', lambda app: None)
    path = manager.install_skill({'name': name, 'entry_point': 'fixture'})
    assert validate_skill(path.parent) == {'valid': True, 'errors': []}
    assert path.parent.name != 'cli-app-research-tools'


@pytest.mark.parametrize('header,newline', [
    ('"name": external-name\ndescription: Use the installed application', '\n'),
    ("'name': external-name\ndescription: Use the installed application", '\r\n'),
    ('description: Use the installed application', '\n'),
])
def test_managed_name_is_written_only_in_yaml_frontmatter(tmp_path, header, newline):
    body = '# Details' + newline + 'name: literal command data' + newline
    source = '---' + newline + header.replace('\n', newline) + newline + '---' + newline + body
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    result = manager._with_cirno_skill_note(source, {'name': 'demo', 'entry_point': 'demo'})
    metadata = parse_skill_metadata(result)
    assert metadata is not None and valid_skill_metadata(metadata, 'cli-app-demo')
    assert metadata['description'] == 'Use the installed application'
    assert body in result
    assert result.count('<!-- cirno-cli-app-note -->') == 1


@pytest.mark.parametrize('order', [('research_tools', 'research-tools'), ('research-tools', 'research_tools')])
def test_distinct_registry_names_cannot_overwrite_or_remove_each_others_skills(tmp_path, monkeypatch, order):
    monkeypatch.setattr('cirno_core.apps.cli.paths.get_home_path', lambda: tmp_path)
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    monkeypatch.setattr(manager, '_fetch_skill_content', lambda app: None)
    first, second = [manager.install_skill({'name': name, 'entry_point': name}) for name in order]
    assert first != second
    for name, path in zip(order, [first, second]):
        assert cli_app_skill_path(name) == path
        assert f'name="{name}"' in path.read_text()
        assert validate_skill(path.parent) == {'valid': True, 'errors': []}
    first_content = first.read_text()
    manager.remove_skill(order[1])
    assert first.read_text() == first_content
    assert cli_app_skill_path(order[0]) == first
    assert not second.exists()


def test_legacy_underscore_owner_keeps_its_directory_when_hyphen_app_is_added(tmp_path, monkeypatch):
    monkeypatch.setattr('cirno_core.apps.cli.paths.get_home_path', lambda: tmp_path)
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    monkeypatch.setattr(manager, '_fetch_skill_content', lambda app: None)
    legacy = tmp_path / 'skills/cli-app-research-tools/SKILL.md'
    legacy.parent.mkdir(parents=True)
    # An old generated Skill has no ownership field in its YAML header.
    legacy.write_text('---\nname: cli-app-research-tools\ndescription: Legacy research\n---\n'
                      '<!-- cirno-cli-app-note -->\n## Cirno execution\n\n'
                      'Use the `apps__run` tool with `name="research_tools"` for command execution.\n')
    assert cli_app_skill_path('research_tools') == legacy
    updated = manager.install_skill({'name': 'research_tools', 'entry_point': 'research'})
    assert updated == legacy
    assert parse_skill_metadata(updated.read_text())['name'] == legacy.parent.name
    other = manager.install_skill({'name': 'research-tools', 'entry_point': 'other'})
    assert other != legacy
    assert cli_app_skill_path('research-tools') == other
    manager.remove_skill('research_tools')
    assert not legacy.exists()
    # Removing the old owner must not move the new owner's published identity.
    assert cli_app_skill_path('research-tools') == other
    assert other.is_file()


@pytest.mark.parametrize('content', [b'\xff\xfe', None])
def test_unreadable_optional_owner_does_not_break_skill_path(tmp_path, monkeypatch, content):
    monkeypatch.setattr('cirno_core.apps.cli.paths.get_home_path', lambda: tmp_path)
    legacy = tmp_path / 'skills/cli-app-research/SKILL.md'
    legacy.parent.mkdir(parents=True)
    if content is None:
        legacy.mkdir()
    else:
        legacy.write_bytes(content)
    resolved = cli_app_skill_path('research')
    assert resolved != legacy
    assert resolved.parent.name.startswith('cli-app-research-')
