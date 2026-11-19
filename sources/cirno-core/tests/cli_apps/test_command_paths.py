"""CLI selections retain their package identity and current project directory."""

import subprocess
import sys

import pytest
from cirno_core.apps.cli import CliAppManager
from cirno_core.apps.cli.contracts import CliAppError


@pytest.mark.parametrize('specification,name', [
    ('example@1.2.3', 'example'), ('@scope/example@1.2.3', '@scope/example'),
    ('@scope/example', '@scope/example'), ('example@next', 'example'),
])
def test_npm_update_replaces_the_existing_version_selector(tmp_path, monkeypatch, specification, name):
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    monkeypatch.setattr('cirno_core.apps.cli.commands.shutil.which', lambda command: '/tools/npm')
    assert manager.commands._npm_argv({'npm_package': specification}, 'update') == [
        '/tools/npm', 'install', '-g', name + '@latest',
    ]


@pytest.mark.parametrize('restricted', [False, True])
def test_relative_working_directory_uses_project_not_service_directory(tmp_path, monkeypatch, restricted):
    project, server = tmp_path / 'project', tmp_path / 'server'
    (project / 'outputs').mkdir(parents=True)
    server.mkdir()
    monkeypatch.chdir(server)
    manager = CliAppManager(workspace=project, data_dir=tmp_path / 'state')
    manager.installed.put('fixture', {'entry_point': sys.executable})
    monkeypatch.setattr(manager.registry, 'get_app', lambda name: {'name': name})
    calls = []

    def run(argv, **kwargs):
        calls.append(kwargs['cwd'])
        return subprocess.CompletedProcess(argv, 0, stdout='done', stderr='')

    monkeypatch.setattr('cirno_core.apps.cli.service.run_cli', run)
    assert 'done' in manager.run('fixture', working_dir='outputs', restrict_to_workspace=restricted)
    assert calls == [(project / 'outputs').resolve()]


def test_relative_working_directory_still_cannot_escape_restricted_project(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    manager = CliAppManager(workspace=project, data_dir=tmp_path / 'state')
    with pytest.raises(CliAppError, match='outside'):
        manager._resolve_cwd('../outside', restrict_to_workspace=True)


@pytest.mark.parametrize('name', ['saved-cli', 'SAVED-CLI'])
def test_installed_cli_runs_without_contacting_the_registry(tmp_path, monkeypatch, name):
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    manager.installed.put('saved-cli', {'entry_point': sys.executable})
    monkeypatch.setattr(manager.registry, 'get_app', lambda *args, **kwargs: pytest.fail('Runtime tried to refresh the external app catalog'))
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='local tool completed', stderr='')

    monkeypatch.setattr('cirno_core.apps.cli.service.run_cli', run)
    assert 'local tool completed' in manager.run(name, ['--version'])
    assert calls == [[sys.executable, '--version']]


def test_cli_discovery_uses_the_managed_python_environment(tmp_path, monkeypatch):
    environment = tmp_path / 'python-tools'
    executable = environment / ('Scripts' if sys.platform == 'win32' else 'bin') / 'research-fixture'
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    executable.chmod(0o755)
    monkeypatch.setenv('CIRNO_SHELL_VENV', str(environment))
    monkeypatch.setenv('PATH', '')
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    app = {'name': 'research', 'entry_point': executable.name, 'package_manager': 'bundled'}
    manager.installed.put('research', app)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='completed', stderr='')

    monkeypatch.setattr('cirno_core.apps.cli.service.run_cli', run)
    assert manager._app_payload(app, manager.installed.read())['available'] is True
    assert manager._installed_entry(app)['entry_point_path'] == str(executable)
    assert 'completed' in manager.run('research')
    assert calls == [[str(executable)]]


def test_installed_distribution_is_read_from_the_tools_environment(tmp_path, monkeypatch):
    from cirno_core.apps.cli import command_support

    environment = tmp_path / 'python-tools'
    site = environment / ('Lib/site-packages' if sys.platform == 'win32' else 'lib/python3.12/site-packages')
    distribution = site / 'research_distribution-1.0.dist-info'
    distribution.mkdir(parents=True)
    (distribution / 'METADATA').write_text('Name: research-distribution\nVersion: 1.0\n', encoding='utf-8')
    (distribution / 'entry_points.txt').write_text('[console_scripts]\nresearch-fixture = research:main\n', encoding='utf-8')
    monkeypatch.setenv('CIRNO_SHELL_VENV', str(environment))
    original_distributions = command_support.importlib_metadata.distributions

    def only_target_environment(**kwargs):
        assert 'path' in kwargs, 'CLI metadata was read from the service environment'
        return original_distributions(**kwargs)

    monkeypatch.setattr(command_support.importlib_metadata, 'distributions', only_target_environment)
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / 'state')
    entry = manager._installed_entry({'name': 'research', 'entry_point': 'research-fixture', 'package_manager': 'pip'})
    assert entry['pip_distribution'] == 'research-distribution'
