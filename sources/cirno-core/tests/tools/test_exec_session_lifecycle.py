from __future__ import annotations

import asyncio
import base64
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.exec_session import ExecSessionTool
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager

from sources.development.testing.processes import (
    extract_session_id,
    python_command,
    waiting_shell_command,
)


def test_exec_session_manager_close_all_terminates_active_sessions(tmp_path):
    async def run() -> None:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=30, session_manager=manager)
        initial = await tool.execute(
            command=waiting_shell_command("ready"),
            yield_time_ms=100,
        )
        sid = extract_session_id(initial)
        process = manager._sessions[sid].process
        assert process.returncode is None

        closed = await manager.close_all()

        assert closed == 1
        assert process.returncode is not None
        assert manager._sessions == {}
        assert await manager.close_all() == 0

    asyncio.run(run())


def test_exec_session_manager_shutdown_terminates_child_processes(tmp_path):
    async def run() -> None:
        marker = tmp_path / "orphaned-child.txt"
        child_code = (
            "import pathlib,time; time.sleep(2); "
            f"pathlib.Path({str(marker)!r}).write_text('alive')"
        )
        child_payload = base64.b64encode(child_code.encode()).decode()
        parent_code = (
            "import base64,subprocess,sys,time; "
            f"child=base64.b64decode('{child_payload}').decode(); "
            "subprocess.Popen([sys.executable, '-c', child]); "
            "print('ready', flush=True); time.sleep(4)"
        )
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=30, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        initial = await tool.execute(command=python_command(parent_code), yield_time_ms=500)
        observed = current = initial
        deadline = time.monotonic() + 5
        while "ready" not in observed and "session_id:" in current:
            assert time.monotonic() < deadline, observed
            await asyncio.sleep(0.05)
            current = await stdin_tool.execute(
                session_id=extract_session_id(initial),
                input="",
                timeout_ms=0,
            )
            observed += f"\n{current}"
        assert "ready" in observed
        assert "Process running" in current

        await manager.close_all()
        await asyncio.sleep(2.3)

        assert not marker.exists()

    asyncio.run(run())


def test_exec_session_manager_rejects_new_sessions_after_shutdown(tmp_path):
    async def run() -> str:
        manager = ExecSessionManager()
        await manager.close_all()
        tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        return await tool.execute(command="echo should-not-run", yield_time_ms=0)

    result = asyncio.run(run())

    assert result == "Error executing command: exec session manager is closed"


def test_exec_session_manager_retains_and_aggregates_failed_cleanup():
    async def run() -> None:
        manager = ExecSessionManager()
        first = SimpleNamespace(
            session_id="first",
            kill=AsyncMock(side_effect=OSError("first failed")),
        )
        second = SimpleNamespace(
            session_id="second",
            kill=AsyncMock(side_effect=RuntimeError("second failed")),
        )
        manager._sessions = {first.session_id: first, second.session_id: second}

        with pytest.raises(ExceptionGroup) as exc_info:
            await manager.close_all()

        assert len(exc_info.value.exceptions) == 2
        assert manager._sessions == {first.session_id: first, second.session_id: second}
        first.kill.assert_awaited_once_with("shutdown")
        second.kill.assert_awaited_once_with("shutdown")

        first.kill.side_effect = None
        second.kill.side_effect = None
        assert await manager.close_all() == 2
        assert manager._sessions == {}

    asyncio.run(run())


def test_exec_session_manager_preserves_single_cleanup_error():
    async def run() -> None:
        manager = ExecSessionManager()
        session = SimpleNamespace(
            session_id="failed",
            kill=AsyncMock(side_effect=OSError("cleanup failed")),
        )
        manager._sessions = {session.session_id: session}

        with pytest.raises(OSError, match="cleanup failed"):
            await manager.close_all()

        assert manager._sessions == {session.session_id: session}

    asyncio.run(run())
