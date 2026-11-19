"""Local app management retains the installed package's identity offline."""

import subprocess
import sys

import pytest
from cirno_core.apps.cli.service import CliAppManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr('cirno_core.apps.cli.paths.get_home_path', lambda: tmp_path / 'home')
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    monkeypatch.setattr(manager.registry, 'get_app', lambda *args, **kwargs: pytest.fail('Local management contacted the external catalog'))

    def catalog(**kwargs):
        assert kwargs.get('cache_only'), 'Local management refreshed the external catalog'
        return [], None

    monkeypatch.setattr(manager.registry, 'catalog', catalog)
    return manager


@pytest.mark.parametrize('strategy,fields,expected', [
    ('npm', {'npm_package': '@lab/research@1.2'}, ['/tools/npm', 'uninstall', '-g', '@lab/research@1.2']),
    ('pip', {'install_cmd': 'pip install research-package'}, ['uv', 'pip', 'uninstall', '--python', sys.executable, 'research-package']),
    ('brew', {'uninstall_cmd': 'brew uninstall research-package'}, ['brew', 'uninstall', 'research-package']),
    ('uv', {'uninstall_cmd': 'uv tool uninstall research-package'}, ['uv', 'tool', 'uninstall', 'research-package']),
])
def test_uninstall_uses_the_installed_definition_without_a_catalog(manager, monkeypatch, strategy, fields, expected):
    monkeypatch.setattr(manager.commands, 'which', lambda name: '/tools/npm' if name == 'npm' else None)
    monkeypatch.setattr('cirno_core.apps.cli.command_support._console_script_distribution', lambda *args, **kwargs: None)
    app = {'name': 'research', 'display_name': 'Research', 'entry_point': 'research-cli', 'package_manager': strategy, **fields}
    manager.installed.put('research', manager._installed_entry(app))
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='removed', stderr='')

    monkeypatch.setattr(manager.commands, '_run_argv', run)
    result = manager.uninstall('RESEARCH')
    assert calls == [expected]
    assert result['last_action']['removed'] is True
    assert result['installed_count'] == 0
    assert not manager.installed.read()


def test_installed_help_check_runs_without_a_catalog(manager, monkeypatch):
    manager.installed.put('research', {'entry_point': sys.executable})
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='local help', stderr='')

    monkeypatch.setattr(manager.commands, '_run_argv', run)
    result = manager.test('RESEARCH')
    assert calls == [[sys.executable, '--help']]
    assert result['last_action']['ok'] is True
    assert result['last_action']['output'] == 'local help'


def test_legacy_removal_retains_the_saved_name_when_catalog_case_changes(manager, monkeypatch):
    manager.installed.put('research', {'entry_point': 'research-cli'})
    monkeypatch.setattr(manager.registry, 'get_app', lambda name: {
        'name': 'RESEARCH', 'display_name': 'Research', 'entry_point': 'research-cli',
        'package_manager': 'pip', 'pip_package': 'research-package',
    })
    monkeypatch.setattr(manager.commands, 'which', lambda name: None)
    monkeypatch.setattr(manager.commands, '_run_argv', lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout='', stderr=''))
    result = manager.uninstall('research')
    assert result['last_action']['removed'] is True
    assert manager.installed.read() == {}


def test_catalog_case_change_does_not_hide_installed_state(manager, monkeypatch):
    manager.installed.put('research', {'entry_point': sys.executable})
    monkeypatch.setattr(manager.registry, 'catalog', lambda **kwargs: ([{
        'name': 'RESEARCH', 'entry_point': sys.executable, 'package_manager': 'bundled',
    }], None))
    result = manager.payload(cache_only=True)
    assert result['installed_count'] == 1
    assert result['apps'][0]['installed'] is True


@pytest.mark.parametrize('action', ['install', 'update'])
def test_catalog_case_change_keeps_one_installed_identity(manager, monkeypatch, action):
    manager.installed.put('research', {'entry_point': 'research-cli'})
    app = {'name': 'RESEARCH', 'display_name': 'Research', 'entry_point': 'research-cli', 'package_manager': 'bundled'}
    monkeypatch.setattr(manager.registry, 'get_app', lambda *args, **kwargs: app)
    monkeypatch.setattr(manager.registry, 'catalog', lambda **kwargs: ([app], None))
    monkeypatch.setattr(manager.commands, 'which', lambda name: '/tools/research-cli')
    monkeypatch.setattr(manager, '_fetch_skill_content', lambda app: None)
    result = getattr(manager, action)('research')
    assert result['last_action']['ok'] is True
    assert set(manager.installed.read()) == {'research'}


@pytest.mark.parametrize('with_other_entry', [False, True])
def test_catalog_listing_keeps_installed_entries_missing_upstream(manager, monkeypatch, with_other_entry):
    manager.installed.put('research', {'entry_point': sys.executable, 'display_name': 'Local research'})
    if with_other_entry:
        monkeypatch.setattr(manager.registry, 'catalog', lambda **kwargs: ([{
            'name': 'other', 'display_name': 'Other available app', 'package_manager': 'bundled',
        }], None))
    result = manager.payload(cache_only=True)
    assert result['installed_count'] == 1
    research = next(row for row in result['apps'] if row['name'] == 'research')
    assert research['installed'] is True


def test_colliding_app_names_keep_independent_listing_attachment_and_uninstall(manager, monkeypatch):
    from cirno_core.apps.cli.utils import runtime_lines_for_request

    monkeypatch.setattr(manager, '_fetch_skill_content', lambda app: None)
    monkeypatch.setattr(manager.commands, 'which', lambda name: None)
    published = {}
    for name in ('research_tools', 'research-tools'):
        app = {'name': name, 'entry_point': name, 'package_manager': 'bundled'}
        manager.installed.put(name, manager._installed_entry(app))
        published[name] = manager.install_skill(app)
    rows = manager.installed_payload()['apps']
    assert len(rows) == 2 and all(row['skill_installed'] for row in rows)
    attached = manager.mentioned_installed_apps('@research_tools @research-tools')
    assert {row['name']: row['skill'] for row in attached} == {
        name: str(path) for name, path in published.items()
    }
    for row in attached:
        rendered = runtime_lines_for_request('', {'cli_apps': [row]}, manager.workspace)
        assert f"skill={row['skill']}" in rendered[0]
    result = manager.uninstall('research_tools')
    assert result['last_action']['removed'] is True
    assert not published['research_tools'].exists()
    assert published['research-tools'].is_file()
    remaining = manager.installed_payload()['apps']
    assert len(remaining) == 1 and remaining[0]['skill_installed'] is True


@pytest.mark.parametrize('strategy,extra,expected', [
    ('bundled', {}, []),
    ('pip', {'pip_distribution': 'actual-research-dist'}, [
        ['uv', 'pip', 'uninstall', '--python', sys.executable, 'actual-research-dist'],
    ]),
])
def test_legacy_removal_uses_known_local_package_identity_offline(manager, monkeypatch, strategy, extra, expected):
    manager.installed.put('research', {'entry_point': 'research-cli', 'strategy': strategy, **extra})
    monkeypatch.setattr(manager.commands, 'which', lambda name: None)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='', stderr='')

    monkeypatch.setattr(manager.commands, '_run_argv', run)
    result = manager.uninstall('research')
    assert result['last_action']['removed'] is True
    assert manager.installed.read() == {}
    assert calls == expected


def test_failed_managed_skill_cleanup_keeps_the_installation_record(manager, monkeypatch):
    entry = {'entry_point': 'research-cli', 'strategy': 'bundled'}
    manager.installed.put('research', entry)
    monkeypatch.setattr(manager.commands, 'which', lambda name: None)

    def fail(name):
        raise OSError('Skill cleanup failed')

    monkeypatch.setattr(manager, 'remove_skill', fail)
    with pytest.raises(OSError, match='Skill cleanup failed'):
        manager.uninstall('research')
    assert manager.installed.read() == {'research': entry}


@pytest.mark.parametrize('legacy_pip', [False, True])
def test_catalog_refresh_cannot_change_saved_executable_or_package_manifest(manager, monkeypatch, legacy_pip):
    app = {'name': 'research', 'display_name': 'Research', 'entry_point': 'approved-cli',
           'package_manager': 'npm', 'npm_package': '@lab/approved@1'}
    monkeypatch.setattr(manager.commands, 'which', lambda name: '/tools/replacement' if name == 'replacement-cli' else '/tools/npm' if name == 'npm' else None)
    manager.installed.put('research', (
        {'entry_point': 'approved-cli', 'strategy': 'pip', 'pip_distribution': 'approved-distribution'}
        if legacy_pip else manager._installed_entry(app)
    ))
    replacement = {**app, 'entry_point': 'replacement-cli', 'npm_package': '@lab/replacement@2'}
    monkeypatch.setattr(manager.registry, 'catalog', lambda **kwargs: ([replacement], None))
    row = manager.payload(cache_only=True)['apps'][0]
    assert row['entry_point'] == 'approved-cli'
    assert row['available'] is False
    capability = row['manifest']['capabilities'][0]
    assert capability['package']['name'] == ('approved-distribution' if legacy_pip else '@lab/approved@1')
