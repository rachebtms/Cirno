from __future__ import annotations

import asyncio

from cirno_core.agent.tools.exec_session import ExecSessionTool
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager

from sources.development.testing.processes import (
    extract_session_id,
    poll_if_running,
    python_command,
    waiting_shell_command,
)


def test_exec_can_continue_with_stdin(tmp_path):
    async def run() -> tuple[str, str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = python_command(
            "import sys; print('ready', flush=True); "
            "line=sys.stdin.readline(); print('got:' + line.strip(), flush=True)"
        )

        try:
            initial = await exec_tool.execute(command=command, yield_time_ms=500)
            sid = extract_session_id(initial)
            result = await stdin_tool.execute(session_id=sid, input="ping\n", timeout_ms=1000)
            observed, final = await poll_if_running(result, stdin_tool)
            return initial, observed, final
        finally:
            await manager.close_all()

    initial, result, final = asyncio.run(run())
    assert "ready" in initial + result
    assert "Process running" in initial
    assert "Elapsed:" in initial
    assert "got:ping" in result
    assert "Exit code: 0" in final
    assert "Elapsed:" in result


def test_exec_session_can_close_stdin(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = python_command(
            "import sys; print('ready', flush=True); "
            "data=sys.stdin.read(); print('got:' + data, flush=True)"
        )

        initial = await exec_tool.execute(command=command, yield_time_ms=1500)
        sid = extract_session_id(initial)
        result = await stdin_tool.execute(
            session_id=sid,
            input="payload",
            close_stdin=True,
            until_exit=True,
            timeout_ms=5000,
        )
        return initial, result

    initial, result = asyncio.run(run())
    assert "ready" in initial + result
    assert "got:payload" in result
    assert "Stdin closed." in result
    assert "Exit code: 0" in result


def test_closed_stdin_acknowledgement_survives_multiple_wait_polls(tmp_path):
    async def run() -> str:
        manager = ExecSessionManager()
        try:
            exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
            stdin_tool = ExecSessionTool(manager=manager)
            command = python_command(
                "import sys,time; print('ready',flush=True); "
                "data=sys.stdin.read(); time.sleep(.7); print('got:' + data,flush=True)"
            )
            initial = await exec_tool.execute(command=command, yield_time_ms=100)
            return await stdin_tool.execute(session_id=extract_session_id(initial), input="payload",
                close_stdin=True, wait_for="got:payload", timeout_ms=5000)
        finally:
            await manager.close_all()

    result = asyncio.run(run())
    assert "got:payload" in result
    assert "Stdin closed." in result


def test_exec_session_can_terminate_session(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=30, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = waiting_shell_command("ready")

        initial = await exec_tool.execute(command=command, yield_time_ms=100)
        sid = extract_session_id(initial)
        if "ready" not in initial:
            initial += await stdin_tool.execute(
                session_id=sid,
                wait_for="ready",
                timeout_ms=10000,
            )
        result = await stdin_tool.execute(
            session_id=sid,
            terminate=True,
        )
        return initial, result

    initial, result = asyncio.run(run())
    assert "ready" in initial
    assert "Session terminated." in result
    assert "Exit code:" in result


def test_exec_session_preserves_completed_session_output_until_polled(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        release = tmp_path / "release"
        command = python_command(
            "import time\nfrom pathlib import Path\n"
            "print('ready', flush=True)\n"
            "while not Path('release').exists(): time.sleep(0.01)\n"
            "print('done', flush=True)\n"
        )
        try:
            initial = await exec_tool.execute(command=command, yield_time_ms=50)
            sid = extract_session_id(initial)
            session = manager._sessions[sid]
            release.touch()
            await asyncio.wait_for(asyncio.shield(session._completion_task), timeout=5)
            assert session.finish_reason == "exit"
            assert session.finished_at is not None
            final = await stdin_tool.execute(session_id=sid, input="", timeout_ms=0)
            return initial, final
        finally:
            release.touch()
            await manager.close_all()

    initial, final = asyncio.run(run())

    assert "ready" in initial + final
    assert "done" in final
    assert "Exit code: 0" in final
