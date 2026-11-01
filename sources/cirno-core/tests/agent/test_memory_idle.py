import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno.memory.idle import MemoryIdleCoordinator
from cirno.config.home import set_home_path
from cirno.config.schema import Config
from cirno.memory.repository import MemoryRepository


@pytest.fixture
def idle(tmp_path):
    set_home_path(tmp_path)
    cfg = Config()
    agent = SimpleNamespace(bus=SimpleNamespace(admission=SimpleNamespace(paused=False), has_pending_events=False),
                            _active_tasks=set(), _background_tasks=set(), _last_memory_activity=time.monotonic()-3600,
                            schedule_background=lambda coro: asyncio.create_task(coro), _idle_memory_task=None)
    runner = AsyncMock()
    coordinator = MemoryIdleCoordinator(agent, cfg, runner)
    yield coordinator, agent, cfg, runner
    set_home_path(None)


@pytest.mark.asyncio
async def test_idle_dream_is_tracked_and_backs_off(idle):
    idle, agent, cfg, runner = idle
    await idle.check()
    await agent._idle_memory_task
    runner.assert_awaited_once()
    await idle.check()
    runner.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("block", ["active", "background", "pending", "admission", "recent", "disabled", "interval"])
async def test_foreground_and_disabled_modes_do_not_start_dream(idle, block):
    idle, agent, cfg, runner = idle
    if block == "active": agent._active_tasks.add("busy")
    if block == "background": agent._background_tasks.add("busy")
    if block == "pending": agent.bus.has_pending_events = True
    if block == "admission": agent.bus.admission.paused = True
    if block == "recent": agent._last_memory_activity = time.monotonic()
    if block == "disabled": cfg.agents.defaults.dream.enabled = False
    if block == "interval": cfg.agents.defaults.dream.mode = "interval"
    await idle.check()
    assert agent._idle_memory_task is None
    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_maintenance_indexes_manual_changes(idle, tmp_path):
    idle, agent, cfg, runner = idle
    cfg.agents.defaults.dream.enabled = False
    repo = MemoryRepository(tmp_path)
    record = repo.save("old", source="test:source", session_key="a")
    (repo.root / "entries" / (record["id"] + ".md")).write_text("new entropy")
    await idle.check()
    assert repo.search("entropy", session_key="a")["memories"]
