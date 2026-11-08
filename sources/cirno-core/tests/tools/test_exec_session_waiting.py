from __future__ import annotations

import asyncio

import pytest
from cirno_core.agent.tools.exec_session import ExecSessionTool, ListExecSessionsTool
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager

from sources.development.testing.processes import (
    extract_session_id,
    python_command,
    waiting_shell_command,
)


def test_exec_session_until_exit_waits_for_silent_process(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        session_tool = ExecSessionTool(manager=manager)
        command = python_command("import time; time.sleep(0.2); print('done', flush=True)")

        initial = await exec_tool.execute(command=command, yield_time_ms=0)
        final = await session_tool.execute(
            session_id=extract_session_id(initial),
            until_exit=True,
            timeout_ms=2000,
        )
        return initial, final

    initial, final = asyncio.run(run())

    assert "Process running" in initial
    assert "done" in final
    assert "Exit code: 0" in final
    assert "Process running" not in final


def test_exec_session_until_exit_aggregates_output_and_reports_nonzero_exit(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        session_tool = ExecSessionTool(manager=manager)
        command = python_command(
            "import sys,time; print('first', flush=True); time.sleep(0.1); "
            "print('second', flush=True); time.sleep(0.1); sys.exit(7)"
        )

        initial = await exec_tool.execute(command=command, yield_time_ms=0)
        final = await session_tool.execute(
            session_id=extract_session_id(initial),
            until_exit=True,
            timeout_ms=2000,
        )
        return initial, final

    initial, final = asyncio.run(run())

    output = initial + final
    assert "first" in output
    assert "second" in output
    assert "Exit code: 7" in final


def test_exec_session_until_exit_timeout_keeps_session_active(tmp_path):
    async def run() -> tuple[str, str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        session_tool = ExecSessionTool(manager=manager)
        initial = await exec_tool.execute(
            command=python_command("import time; time.sleep(0.3); print('done', flush=True)"),
            yield_time_ms=0,
        )
        sid = extract_session_id(initial)
        timed_wait = await session_tool.execute(
            session_id=sid,
            until_exit=True,
            timeout_ms=20,
        )
        final = await session_tool.execute(
            session_id=sid,
            until_exit=True,
            timeout_ms=2000,
        )
        return initial, timed_wait, final

    initial, timed_wait, final = asyncio.run(run())

    assert "Process running" in initial
    assert "Process running" in timed_wait
    assert "Wait timed out after 0.02s; session remains active." in timed_wait
    assert "done" in final
    assert "Exit code: 0" in final


def test_exec_session_until_exit_can_be_cancelled_without_losing_session(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        session_tool = ExecSessionTool(manager=manager)
        list_tool = ListExecSessionsTool(manager=manager)
        initial = await exec_tool.execute(
            command=python_command("import time; time.sleep(5)"),
            yield_time_ms=0,
        )
        sid = extract_session_id(initial)
        wait_task = asyncio.create_task(
            session_tool.execute(
                session_id=sid,
                until_exit=True,
                timeout_ms=2000,
            )
        )
        await asyncio.sleep(0.05)
        wait_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await wait_task
        listing = await list_tool.execute()
        cleanup = await session_tool.execute(session_id=sid, terminate=True)
        return listing, cleanup

    listing, cleanup = asyncio.run(run())

    assert "running" in listing
    assert "Session terminated." in cleanup


def test_exec_session_rejects_conflicting_wait_conditions():
    async def run() -> str:
        return await ExecSessionTool().execute(
            session_id="unused",
            wait_for="ready",
            until_exit=True,
        )

    result = asyncio.run(run())

    assert result == "Error: wait_for and until_exit are mutually exclusive."
    assert is_tool_error_result(result)


def test_exec_session_rejects_terminate_with_other_actions():
    async def run() -> str:
        return await ExecSessionTool().execute(
            session_id="unused",
            input="quit\n",
            terminate=True,
        )

    result = asyncio.run(run())

    assert result == "Error: terminate must be used alone."
    assert is_tool_error_result(result)


def test_exec_session_can_wait_for_expected_output(tmp_path):
    async def run() -> tuple[str, str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = waiting_shell_command("booting", delayed="ready")

        initial = await exec_tool.execute(command=command, yield_time_ms=100)
        sid = extract_session_id(initial)
        waited = await stdin_tool.execute(
            session_id=sid,
            input="\n",
            wait_for="ready",
            timeout_ms=1000,
        )
        cleanup = await stdin_tool.execute(session_id=sid, terminate=True)
        return initial, waited, cleanup

    initial, waited, cleanup = asyncio.run(run())

    assert "Process running" in initial
    assert "booting" in initial + waited
    assert "ready" in waited
    assert "Wait target not observed" not in waited
    assert "Session terminated." in cleanup


def test_exec_session_wait_for_reports_timeout_without_killing_session(tmp_path):
    async def run() -> tuple[str, str, str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = waiting_shell_command("booting", delayed="ready")

        initial = await exec_tool.execute(command=command, yield_time_ms=0)
        sid = extract_session_id(initial)
        # Synchronize on an stdin-gated marker before exercising the immediate timeout below.
        ready = await stdin_tool.execute(
            session_id=sid,
            input="\n",
            wait_for="ready",
            timeout_ms=10000,
        )
        waited = await stdin_tool.execute(
            session_id=sid,
            wait_for="never-ready",
            timeout_ms=0,
        )
        cleanup = await stdin_tool.execute(session_id=sid, terminate=True)
        return initial, ready, waited, cleanup

    initial, ready, waited, cleanup = asyncio.run(run())

    assert "Process running" in initial
    assert "booting" in initial + ready
    assert "ready" in ready
    assert "Process running" in waited
    assert "Wait target not observed: 'never-ready'" in waited
    assert "Session terminated." in cleanup
