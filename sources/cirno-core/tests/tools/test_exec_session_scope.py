from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager

from sources.development.testing.processes import (
    extract_session_id,
    python_command,
    waiting_shell_command,
)


def test_terminate_by_owner_kills_matching_sessions(tmp_path):
    async def run() -> None:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=30, session_manager=manager)

        token_a = bind_request_context(
            RequestContext(channel="cli", chat_id="a", session_key="cli:a")
        )
        try:
            initial_a = await tool.execute(
                command=waiting_shell_command("a_ready"),
                yield_time_ms=100,
            )
        finally:
            reset_request_context(token_a)
        sid_a = extract_session_id(initial_a)

        token_b = bind_request_context(
            RequestContext(channel="cli", chat_id="b", session_key="cli:b")
        )
        try:
            initial_b = await tool.execute(
                command=waiting_shell_command("b_ready"),
                yield_time_ms=100,
            )
        finally:
            reset_request_context(token_b)
        sid_b = extract_session_id(initial_b)

        proc_a = manager._sessions[sid_a].process
        proc_b = manager._sessions[sid_b].process
        assert proc_a.returncode is None
        assert proc_b.returncode is None

        killed = await manager.terminate_by_owner("cli:a")

        assert killed == 1
        assert proc_a.returncode is not None
        assert proc_b.returncode is None
        assert sid_a not in manager._sessions
        assert sid_b in manager._sessions

        await manager.close_all()

    asyncio.run(run())


def test_terminate_by_owner_returns_zero_for_no_match(tmp_path):
    async def run() -> None:
        manager = ExecSessionManager()
        killed = await manager.terminate_by_owner("nonexistent")
        assert killed == 0
        assert manager._sessions == {}

    asyncio.run(run())


def test_terminate_by_owner_retains_failed_sessions():
    async def run() -> None:
        manager = ExecSessionManager()
        session = SimpleNamespace(
            session_id="failed",
            owner_session_key="cli:a",
            kill=AsyncMock(side_effect=OSError("termination failed")),
        )
        manager._sessions[session.session_id] = session

        with pytest.raises(OSError, match="termination failed"):
            await manager.terminate_by_owner("cli:a")

        assert manager._sessions == {session.session_id: session}
        session.kill.assert_awaited_once_with("owner_closed")

        session.kill.side_effect = None
        assert await manager.terminate_by_owner("cli:a") == 1
        assert manager._sessions == {}

    asyncio.run(run())


def test_result_retention_only_cleans_completed_sessions(tmp_path, monkeypatch):
    async def run() -> None:
        now = time.monotonic()
        monkeypatch.setattr(
            "cirno_core.processes.sessions.manager.time",
            SimpleNamespace(monotonic=lambda: now),
        )
        monkeypatch.setattr(
            "cirno_core.processes.sessions.session.time",
            SimpleNamespace(monotonic=lambda: now),
        )
        manager = ExecSessionManager(result_retention=10)
        tool = ExecTool(working_dir=str(tmp_path), max_runtime=0, session_manager=manager)
        command = python_command(
            "import sys; print('ready', flush=True); "
            "sys.stdin.read(); print('done', flush=True)"
        )

        try:
            initial = await tool.execute(command=command, yield_time_ms=0)
            sid = extract_session_id(initial)
            session = manager._sessions[sid]

            now += 100
            listing = await manager.list()
            assert [info.session_id for info in listing] == [sid]
            assert session.process.returncode is None
            assert session.finished_at is None

            assert await session.close_stdin() is None
            await asyncio.wait_for(session._completion_task, timeout=10)
            assert session.finish_reason == "exit"
            assert session.finished_at == now
            assert session._stdout.has_output

            now += 9
            listing = await manager.list()
            assert [info.session_id for info in listing] == [sid]
            assert listing[0].finish_reason == "exit"
            assert listing[0].returncode == 0

            now += 2
            assert await manager.list() == []
            assert manager._sessions == {}
        finally:
            await manager.close_all()

    asyncio.run(run())


def test_terminate_by_owner_skips_sessions_without_owner_key(tmp_path):
    async def run() -> None:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=30, session_manager=manager)

        # Spawn without owner (no request context)
        initial = await tool.execute(
            command=waiting_shell_command("ready"),
            yield_time_ms=100,
        )
        sid = extract_session_id(initial)
        proc = manager._sessions[sid].process
        assert proc.returncode is None

        killed = await manager.terminate_by_owner("cli:a")

        assert killed == 0
        assert proc.returncode is None
        assert sid in manager._sessions

        await manager.close_all()

    asyncio.run(run())
