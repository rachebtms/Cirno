"""Idle indexing is local; learning runs only inside context consolidation."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cirno_core.memory.idle import MemoryIdleCoordinator
from cirno_core.config.home import set_instance_path
from cirno_core.config.schema import Config
from cirno_memory.repository import MemoryRepository


@pytest.fixture
def idle(tmp_path):
    set_instance_path(tmp_path)
    agent = SimpleNamespace(bus=SimpleNamespace(admission=SimpleNamespace(paused=False), has_pending_events=False),
                            _active_tasks=set(), _background_tasks=set(), schedule_background=MagicMock())
    coordinator = MemoryIdleCoordinator(agent, Config())
    yield coordinator, agent
    set_instance_path(None)


async def test_idle_maintenance_never_starts_an_independent_model_run(idle):
    coordinator, agent = idle
    await coordinator.check()
    await coordinator.check()
    agent.schedule_background.assert_not_called()


@pytest.mark.parametrize("block", ["active", "background", "pending", "admission"])
async def test_busy_runtime_defers_local_index_maintenance(idle, block, monkeypatch):
    coordinator, agent = idle
    if block == "active": agent._active_tasks.add("busy")
    if block == "background": agent._background_tasks.add("busy")
    if block == "pending": agent.bus.has_pending_events = True
    if block == "admission": agent.bus.admission.paused = True
    reconcile = MagicMock()
    monkeypatch.setattr(MemoryRepository, "reconcile", reconcile)
    await coordinator.check()
    reconcile.assert_not_called()
    agent.schedule_background.assert_not_called()


async def test_idle_maintenance_indexes_manual_changes(idle, tmp_path):
    coordinator, agent = idle
    repo = MemoryRepository(tmp_path / "home")
    record = repo.save("old", source="test:source", session_key="a")
    (repo.root / "entries" / (record["id"] + ".md")).write_text("new entropy")
    await coordinator.check()
    assert repo.search("entropy", session_key="a")["memories"]
    agent.schedule_background.assert_not_called()
