from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager

from sources.development.testing.processes import (
    extract_session_id,
    waiting_shell_command,
)


def test_agent_loop_shutdown_closes_exec_sessions(tmp_path):
    async def run() -> None:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=30, session_manager=manager)
        initial = await tool.execute(
            command=waiting_shell_command("ready"),
            yield_time_ms=100,
        )
        sid = extract_session_id(initial)
        process = manager._sessions[sid].process

        loop = object.__new__(AgentLoop)
        from cirno_core.agent.execution.lifecycle import AgentLifecycle
        loop.lifecycle = AgentLifecycle(loop)
        loop.sessions = SimpleNamespace(state=SimpleNamespace(aclose=AsyncMock()))
        loop._background_tasks = set()
        loop._exec_session_manager = manager
        loop.runtime_resolver = SimpleNamespace(aclose=AsyncMock())
        loop.subagents = SimpleNamespace(close=AsyncMock())

        await loop.aclose()
        await loop.aclose()

        assert process.returncode is not None
        assert manager._sessions == {}
        assert loop.subagents.close.await_count == 2

    asyncio.run(run())


def test_agent_loop_shutdown_attempts_all_cleanup_after_errors():
    async def run() -> None:
        loop = object.__new__(AgentLoop)
        from cirno_core.agent.execution.lifecycle import AgentLifecycle
        loop.lifecycle = AgentLifecycle(loop)
        loop.sessions = SimpleNamespace(state=SimpleNamespace(aclose=AsyncMock()))
        loop._background_tasks = set()
        loop.runtime_resolver = SimpleNamespace(aclose=AsyncMock())
        loop.subagents = SimpleNamespace(
            close=AsyncMock(side_effect=RuntimeError("subagent cleanup failed")),
        )
        loop._exec_session_manager = SimpleNamespace(
            close_all=AsyncMock(side_effect=OSError("exec cleanup failed")),
        )
        with pytest.raises(BaseExceptionGroup) as exc_info:
            await loop.aclose()

        assert len(exc_info.value.exceptions) == 2
        loop.subagents.close.assert_awaited_once()
        loop._exec_session_manager.close_all.assert_awaited_once()

    asyncio.run(run())


def test_agent_loop_shutdown_preserves_single_cleanup_error():
    async def run() -> None:
        loop = object.__new__(AgentLoop)
        from cirno_core.agent.execution.lifecycle import AgentLifecycle
        loop.lifecycle = AgentLifecycle(loop)
        loop.sessions = SimpleNamespace(state=SimpleNamespace(aclose=AsyncMock()))
        loop._background_tasks = set()
        loop.runtime_resolver = SimpleNamespace(aclose=AsyncMock())
        loop.subagents = SimpleNamespace(
            close=AsyncMock(side_effect=RuntimeError("subagent cleanup failed")),
        )
        loop._exec_session_manager = SimpleNamespace(close_all=AsyncMock())
        with pytest.raises(RuntimeError, match="subagent cleanup failed"):
            await loop.aclose()

        loop._exec_session_manager.close_all.assert_awaited_once()

    asyncio.run(run())
