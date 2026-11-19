"""Node maintenance uses owned storage and drains accepted thread writes on cancellation."""

import asyncio
from datetime import datetime, timezone
from threading import Event
from types import SimpleNamespace

import pytest
from cirno_core.nodes.jobs import NodeJobs
from cirno_core.nodes.monitor import NodeJobMonitor, monitor_node_jobs
from cirno_core.nodes.policy import NodeJobPolicy
from cirno_core.storage.instance import InstanceData


async def test_check_error_write_finishes_before_cancellation_returns(tmp_path, monkeypatch):
    data = InstanceData(tmp_path)
    job = data.save('node_jobs', {'node_id': 'fake-node', 'state': 'running'})
    entered, release = Event(), Event()
    update = data.update
    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return update(*args, **kwargs)
    monkeypatch.setattr(data, 'update', delayed)
    jobs = NodeJobs(SimpleNamespace(data=data))
    task = asyncio.create_task(jobs.record_check_error([job], datetime.now(timezone.utc), RuntimeError('Fake disconnect')))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert data.get('node_jobs', job['id'])['check_error'] == 'Fake disconnect'
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_retention_write_finishes_before_monitor_cancellation_returns(tmp_path, monkeypatch):
    import cirno_core.nodes.monitor as module
    entered, release = Event(), Event()
    finished = []
    def delayed(*args):
        entered.set()
        assert release.wait(2)
        finished.append(True)
        return 0
    monkeypatch.setattr(module, 'prune_records', delayed)
    monitor = NodeJobMonitor(SimpleNamespace(data=InstanceData(tmp_path)))
    task = asyncio.create_task(monitor.cycle(NodeJobPolicy(poll_interval_seconds=0)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished == [True]
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_monitor_factory_uses_the_server_instance_directory(tmp_path, monkeypatch):
    import cirno_core.nodes.monitor as module
    selected, ran = [], []
    def nodes(data=None):
        selected.append(data.state_dir if data is not None else tmp_path / 'wrong-ambient')
        return SimpleNamespace(data=data)
    class Monitor:
        def __init__(self, nodes):
            self.nodes = nodes
        async def run(self):
            ran.append(self.nodes.data.state_dir)
    monkeypatch.setattr(module, 'Nodes', nodes)
    monkeypatch.setattr(module, 'NodeJobMonitor', Monitor)
    await monitor_node_jobs(state_dir=tmp_path / 'owned-state')
    assert selected == ran == [tmp_path / 'owned-state']
