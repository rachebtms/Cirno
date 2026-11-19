"""Incomplete npm metadata must trigger repair, not crash or look ready."""

import json
from pathlib import Path

import pytest
from cirno_setup.backends import npm
from cirno_setup.context import Context
from cirno_setup.planner import Step
from cirno_setup.policy import Policy
from cirno_setup.recipe import Recipe
from cirno_setup.runner import ensure


@pytest.mark.parametrize('metadata', ['', '{"version":', '[]', '{}'])
@pytest.mark.parametrize('specification', ['demo', 'demo@1.2.3'])
def test_corrupt_package_metadata_is_repaired_on_resume(tmp_path, monkeypatch, metadata, specification):
    context = Context(tmp_path, Path(__file__).parents[1] / 'src/cirno_setup/assets', Policy())
    path = context.root / 'npm/lib/node_modules/demo/package.json'
    path.parent.mkdir(parents=True)
    path.write_text(metadata)
    recipe = Recipe('npm', (specification,))
    assert not npm.verify(context, recipe).ready
    monkeypatch.setattr('cirno_setup.runner.os.geteuid', lambda: 1000)
    calls = []

    def install(arguments):
        calls.append(arguments)
        path.write_text(json.dumps({'name': 'demo', 'version': '1.2.3'}))

    monkeypatch.setattr(context, 'run', install)
    ensure(context, [], steps=[Step('npm.demo', recipe)], verify_after=True)
    assert len(calls) == 1
    assert calls[0][:3] == ['npm', 'install', '--global']
    assert json.loads((context.root / 'setup.json').read_text())['status'] == 'ready'
