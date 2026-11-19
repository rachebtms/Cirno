"""Settings actions settle accepted local writes without blocking the event loop."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import set_config_path
from cirno_server.webui.instance_api import instance_action


async def test_instance_initialization_uses_the_request_configuration_state(tmp_path, monkeypatch):
    from cirno_core.config.paths import get_data_dir

    first, second = tmp_path / "first", tmp_path / "second"
    set_instance_path(first)
    set_config_path(second / "config.json")

    def data(state_dir=None):
        return SimpleNamespace(state_dir=state_dir if state_dir is not None else get_data_dir())

    monkeypatch.setattr("cirno_server.webui.instance_api.InstanceData", data)
    monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", lambda data: SimpleNamespace(
        catalog=lambda: {"state_dir": str(data.state_dir)},
    ))
    result = await instance_action({"action": "nodes.list"}, sessions=None, bus=None, config_path=first / "server.json")
    assert result["state_dir"] == str(first / "state")


@pytest.mark.parametrize("stage", ["initialize", "memory.reindex", "memory.retry", "skills.validate", "nodes.settings.save", "nodes.save", "nodes.delete"])
@pytest.mark.parametrize("fails", [False, True])
async def test_cancelled_instance_action_waits_for_accepted_local_write(tmp_path, monkeypatch, stage, fails):
    set_instance_path(tmp_path / "instance")
    set_config_path(tmp_path / "instance" / "config.json")
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    marker = tmp_path / "accepted-local-write"

    def write(*_args, **_kwargs):
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2), "Fixture did not release accepted work"
            marker.write_text("settled", encoding="utf-8")
            if fails:
                raise OSError("Fixture late write failure")
            return {}
        finally:
            completed.set()

    if stage == "initialize":
        monkeypatch.setattr("cirno_server.webui.instance_api.InstanceData", write)
    elif stage == "memory.reindex":
        monkeypatch.setattr("cirno_memory.repository.MemoryRepository.reconcile", write)
    elif stage == "memory.retry":
        monkeypatch.setattr("cirno_core.memory.consolidation_receipts.retry_learning", write)
    elif stage == "skills.validate":
        monkeypatch.setattr("cirno_server.webui.instance_api.inspect_skill", write)
    elif stage == "nodes.settings.save":
        monkeypatch.setattr("cirno_core.nodes.policy.save_policy", write)
    else:
        nodes = SimpleNamespace(save_node=write, remove_node=write, list_nodes=lambda: [])
        monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", lambda _data: nodes)
    action = "nodes.list" if stage == "initialize" else stage
    task = asyncio.create_task(instance_action({"action": action, "values": {"name": "fixture", "id": "fixture"}}, sessions=None, bus=None))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done, "Cancellation returned before the accepted write settled"
    finally:
        release.set()
        await asyncio.to_thread(completed.wait, 1)
        await asyncio.gather(task, return_exceptions=True)
    assert marker.read_text() == "settled"
    assert task.cancelled()


@pytest.mark.parametrize("action", ["nodes.list", "nodes.save", "nodes.delete", "nodes.scan", "nodes.execute", "nodes.test", "nodes.job", "nodes.stop"])
async def test_node_settings_initialization_does_not_block_other_work(tmp_path, monkeypatch, action):
    loop = asyncio.get_running_loop()

    class Nodes:
        def __init__(self, _data):
            responsive = threading.Event()
            loop.call_soon_threadsafe(responsive.set)
            assert responsive.wait(0.2), "Node credential setup blocked the event loop"

        def catalog(self):
            return {"nodes": []}

        def save_node(self, _values):
            return {"id": "fixture"}

        def list_nodes(self):
            return []

        def remove_node(self, _identifier):
            pass

        async def scan_host_key(self, *_args):
            return {"key": "fixture"}

        async def execute_command(self, *_args, **_kwargs):
            return SimpleNamespace(to_dict=lambda: {"exit_code": 0}, output="fixture", connection_warning=None)

        async def execute(self, *_args):
            return "fixture"

        async def inspect_job(self, *_args, **_kwargs):
            return {"id": "fixture", "state": "completed"}

    monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", Nodes)
    result = await instance_action({"action": action, "values": {"id": "fixture", "host": "fixture", "command": "fixture"}},
                                   sessions=None, bus=None)
    assert isinstance(result, dict)
