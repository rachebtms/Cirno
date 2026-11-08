"""Cancellation still stops execution when its durable status write fails."""

import asyncio
from unittest.mock import MagicMock

import pytest

from cirno_core.agent.runner.contracts import AgentRunResult
from cirno_core.agent.subagents.manager import SubagentManager
from cirno_core.bus.queue import MessageBus
from cirno_core.memory.consolidation import Consolidator
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.generation import GenerationSettings
from cirno_core.session.manager import SessionManager
from cirno_core.utils.llm_runtime import LLMRuntime


async def test_failed_stopping_status_write_does_not_leave_the_model_running(tmp_path, monkeypatch):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    await sessions.state.get("owner")
    manager = SubagentManager(
        tmp_path, MessageBus(), 16000, consolidator=MagicMock(spec=Consolidator),
        session_manager=sessions,
    )
    provider = MagicMock(spec=LLMProvider)
    provider.generation = GenerationSettings()
    runtime = LLMRuntime.capture(provider, "fixture", context_window_tokens=128000)
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def held_model(spec):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return AgentRunResult(messages=[], final_content="Finished after release")

    manager.execution.runner.run = held_model
    try:
        await manager.spawn("Pending model request", session_key="owner", runtime=runtime)
        await asyncio.wait_for(entered.wait(), 2)
        task_id, = manager._running_tasks
        original = sessions.state.update_metadata
        failed = False

        async def save(key, updates, **kwargs):
            nonlocal failed
            if not failed and updates.get("subagent_task", {}).get("state") == "stopping":
                failed = True
                raise OSError("Fixture status write failed")
            return await original(key, updates, **kwargs)

        monkeypatch.setattr(sessions.state, "update_metadata", save)
        with pytest.raises(OSError, match="Fixture status write failed"):
            await manager.cancel(task_id, "owner")
        await asyncio.wait_for(cancelled.wait(), .5)
        assert manager.check(task_id, "owner").state == "cancelled"
        assert manager.get_running_count() == 0
    finally:
        release.set()
        await manager.close()
        await asyncio.gather(*manager._running_tasks.values(), return_exceptions=True)
        await sessions.state.aclose()
