"""Python readiness owns a framed metadata record, separate from import output."""

import importlib
import importlib.metadata
import json
import subprocess
import sys
from contextlib import redirect_stdout
from email.message import Message
from io import StringIO
from types import SimpleNamespace

import pytest
from cirno_setup.backends import pip
from cirno_setup.context import Context
from cirno_setup.policy import Policy
from cirno_setup.recipe import Recipe


@pytest.mark.parametrize("shutdown_output", ["", "Library shutdown message\n"])
@pytest.mark.parametrize("incomplete_metadata", [False, True])
def test_import_messages_do_not_corrupt_dependency_metadata(tmp_path, monkeypatch, shutdown_output, incomplete_metadata):
    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0))
    metadata = Message()
    metadata['Name'] = 'noisy-package'
    distribution = SimpleNamespace(metadata=metadata, version='1.0', requires=[])
    entries = [distribution]
    if incomplete_metadata:
        entries.insert(0, SimpleNamespace(metadata=Message(), version='0.0', requires=[]))
    original_import = importlib.import_module

    def noisy_import(name):
        if name == 'noisy_package':
            print('Loading optional library...')
            return SimpleNamespace()
        return original_import(name)

    def inspect(arguments, **kwargs):
        output = StringIO()
        with monkeypatch.context() as patch:
            patch.setattr(sys, 'argv', ['-c', *arguments[3:]])
            patch.setattr(importlib, 'import_module', noisy_import)
            patch.setattr(importlib.metadata, 'distributions', lambda: entries)
            with redirect_stdout(output):
                exec(arguments[2], {})
        return subprocess.CompletedProcess(arguments, 0, stdout=output.getvalue() + shutdown_output, stderr='')

    monkeypatch.setattr(context, 'inspect', inspect)
    assert pip.verify(context, Recipe('pip', ('noisy-package',), imports=('noisy_package',))).ready


def test_corrupt_required_dependency_metadata_reaches_standard_install_and_reverify(tmp_path, monkeypatch):
    from cirno_setup.planner import Step
    from cirno_setup.runner import ensure

    context = Context(tmp_path, tmp_path, Policy(timeout_seconds=0))
    (tmp_path / 'artifacts.json').write_text('{}')
    dependencies = ['broken dependency [']
    calls = []

    def inspect(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout=pip.METADATA_PREFIX + json.dumps([
            ['demo', '1', dependencies, []],
        ]), stderr='')

    def install(arguments, **_kwargs):
        calls.append(arguments)
        dependencies.clear()

    monkeypatch.setattr(context, 'inspect', inspect)
    monkeypatch.setattr(context, 'run', install)
    monkeypatch.setattr('cirno_setup.runner.os.geteuid', lambda: 1000)
    ensure(context, [], steps=[Step('pip.demo', Recipe('pip', ('demo',)))], verify_after=True)
    assert len(calls) == 1
    assert calls[0][:3] == ['uv', 'pip', 'install']
    assert '--reinstall-package' in calls[0]
    assert json.loads((context.root / 'setup.json').read_text())['status'] == 'ready'
