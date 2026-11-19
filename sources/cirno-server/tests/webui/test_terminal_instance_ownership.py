"""A terminal must resolve Node credentials in its server instance, not ambient config."""

from pathlib import Path
from types import SimpleNamespace

import cirno_server.webui.terminals as terminals
import pytest
from cirno_server.webui.workbench_api import WorkbenchAPI


def node_probe(monkeypatch, ambient: Path):
    selected = []
    def nodes(data=None):
        selected.append(data.state_dir if data is not None else ambient)
        raise RuntimeError('Stopped before SSH or process creation')
    monkeypatch.setattr(terminals, 'Nodes', nodes)
    return selected


async def test_workbench_terminal_uses_its_explicit_instance_for_remote_credentials(tmp_path, monkeypatch):
    source = tmp_path / 'owner' / 'config.json'
    selected = node_probe(monkeypatch, tmp_path / 'ambient' / 'state')
    api = WorkbenchAPI(SimpleNamespace(), None, source_config_path=source)
    with pytest.raises(RuntimeError, match='Stopped before SSH'):
        await api.terminals.create(cwd=str(tmp_path), node_id='fake-node')
    assert selected == [source.parent / 'state']


async def test_standalone_terminal_captures_default_instance_before_ambient_change(tmp_path, monkeypatch):
    owner, later = tmp_path / 'owner-state', tmp_path / 'later-state'
    monkeypatch.setattr(terminals, 'get_data_dir', lambda: owner, raising=False)
    manager = terminals.Terminals()
    monkeypatch.setattr(terminals, 'get_data_dir', lambda: later)
    selected = node_probe(monkeypatch, later)
    with pytest.raises(RuntimeError, match='Stopped before SSH'):
        await manager.create(cwd=str(tmp_path), node_id='fake-node')
    assert selected == [owner]
