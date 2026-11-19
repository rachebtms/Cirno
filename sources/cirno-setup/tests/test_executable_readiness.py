"""Readiness checks permissions without launching native installation tools."""

import json
import subprocess

import pytest
from cirno_setup.backends import brew, homebrew, npm, pip
from cirno_setup.context import Context
from cirno_setup.planner import Step
from cirno_setup.policy import Policy
from cirno_setup.recipe import Recipe
from cirno_setup.runner import ensure


@pytest.mark.parametrize('provider', ['pip', 'npm', 'brew', 'homebrew'])
@pytest.mark.parametrize('mode,ready', [(0o644, False), (0o755, True)])
def test_declared_command_must_be_executable(tmp_path, monkeypatch, provider, mode, ready):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0))
    prefix = tmp_path / 'brew'
    monkeypatch.setattr(brew, 'PREFIX', prefix)
    monkeypatch.setattr(homebrew, 'PREFIX', prefix)
    recipe = Recipe(provider, ('demo',), commands=('demo',))
    if provider == 'pip':
        command = context.python.parent / 'demo'
        metadata = json.dumps([['demo', '1', [], []]])
        monkeypatch.setattr(context, 'inspect', lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, stdout=pip.METADATA_PREFIX + metadata, stderr='',
        ))
    elif provider == 'npm':
        command = context.root / 'npm/bin/demo'
        metadata_path = context.root / 'npm/lib/node_modules/demo/package.json'
        metadata_path.parent.mkdir(parents=True)
        metadata_path.write_text('{"version":"1"}')
    elif provider == 'brew':
        command = prefix / 'bin/demo'
        receipt = prefix / 'Cellar/demo/1/INSTALL_RECEIPT.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text('{}')
    else:
        command = prefix / 'bin/brew'
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text('#!/bin/sh\nexit 0\n')
    command.chmod(mode)
    backend = {'pip': pip, 'npm': npm, 'brew': brew, 'homebrew': homebrew}[provider]
    assert backend.verify(context, recipe).ready is ready
    assert command.stat().st_mode & 0o777 == mode, 'Verification must not repair or mutate files'
    if not ready and provider != 'homebrew':
        (tmp_path / 'artifacts.json').write_text('{}')
        monkeypatch.setattr('cirno_setup.runner.os.geteuid', lambda: 1000)
        calls = []

        def repair(arguments, **kwargs):
            calls.append(arguments)
            command.chmod(0o755)

        monkeypatch.setattr(context, 'run', repair)
        ensure(context, [], steps=[Step(f'{provider}.demo', recipe)], verify_after=True)
        assert len(calls) == 1
        assert json.loads((context.root / 'setup.json').read_text())['status'] == 'ready'


def test_homebrew_install_repairs_only_the_managed_script_execute_bit(tmp_path, monkeypatch):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0))
    monkeypatch.setattr(homebrew, 'PREFIX', tmp_path)
    script = tmp_path / 'Homebrew/bin/brew'
    script.parent.mkdir(parents=True)
    script.write_text('#!/bin/sh\nexit 0\n')
    script.chmod(0o640)
    command = tmp_path / 'bin/brew'
    command.parent.mkdir()
    command.symlink_to(script)
    monkeypatch.setattr(context, 'run', lambda *_args, **_kwargs: pytest.fail('Existing Homebrew must not be downloaded again'))
    recipe = Recipe('homebrew')
    assert not homebrew.verify(context, recipe).ready
    homebrew.install(context, recipe)
    assert homebrew.verify(context, recipe).ready
    assert script.stat().st_mode & 0o777 == 0o740
