from __future__ import annotations

import asyncio
import sys

import pytest
from cirno_core.agent.tools.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from cirno_core.agent.tools.exec_session import ExecSessionTool, ListExecSessionsTool
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions import ExecSessionManager

from sources.development.testing.processes import (
    extract_session_id,
    poll_if_running,
    python_command,
    waiting_shell_command,
)


@pytest.mark.parametrize("diagnostic", [False, True], ids=["silent", "error-output"])
def test_exec_default_observation_returns_live_session(tmp_path, diagnostic):
    async def run() -> None:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=20, session_manager=manager)
        observer = ExecSessionTool(manager=manager)
        release = tmp_path / "release"
        command = python_command(
            "import sys,time\n"
            "from pathlib import Path\n"
            "assert sys.stdin.read() == ''\n"
            + ("print('locator failed', file=sys.stderr, flush=True)\n" if diagnostic else "")
            + "print('ready with stdin EOF', flush=True)\n"
            "while not Path('release').exists(): time.sleep(0.01)\n"
            "print('released', flush=True)\n"
            "sys.exit(7)"
        )
        try:
            initial = await asyncio.wait_for(tool.execute(command=command), timeout=5)
            sid = extract_session_id(initial)
            assert "Initial wait ended; session remains active." in initial
            assert "Elapsed:" in initial
            assert "Runtime remaining:" in initial
            combined = initial
            expected = ["ready with stdin EOF"]
            if diagnostic:
                expected.append("locator failed")
            for marker in expected:
                if marker not in combined:
                    combined += await observer.execute(session_id=sid, wait_for=marker)
            assert "ready with stdin EOF" in combined
            if diagnostic:
                assert "locator failed" in combined
            assert "released" not in combined
            release.touch()
            final = await observer.execute(session_id=sid, until_exit=True, timeout_ms=5000)
            assert "released" in final
            assert "Exit code: 7" in final
        finally:
            release.touch()
            await manager.close_all()

    asyncio.run(run())


def test_exec_short_command_returns_output_and_exit_code(tmp_path):
    async def run() -> str:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        try:
            initial = await tool.execute(command="echo hello")
            combined, _ = await poll_if_running(initial, ExecSessionTool(manager=manager), timeout_ms=5000)
            return combined
        finally:
            await manager.close_all()

    result = asyncio.run(run())

    assert "hello" in result
    assert "Exit code: 0" in result


def test_trusted_user_shell_waits_for_complete_result(tmp_path):
    async def run() -> str:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=10, session_manager=manager)
        try:
            return await tool.execute_to_completion(
                command=python_command("import time,sys; time.sleep(1.2); print('user result'); sys.exit(7)"),
                working_dir=str(tmp_path),
            )
        finally:
            await manager.close_all()

    result = asyncio.run(run())
    assert "user result" in result
    assert "Exit code: 7" in result
    assert "session_id:" not in result


def test_exec_accepts_command_aliases(tmp_path):
    async def run() -> str:
        tool = ExecTool(working_dir="/")
        return await tool.execute(
            cmd=python_command("import os; print(os.getcwd())"),
            workdir=str(tmp_path), yield_time_ms=10000,
        )

    result = asyncio.run(run())

    assert str(tmp_path) in result
    assert "Exit code: 0" in result


def test_exec_returns_completed_session_output_when_yield_time_ms_is_used(tmp_path):
    async def run() -> tuple[str, str]:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)

        initial = await tool.execute(command="echo hello", yield_time_ms=1000)
        return await poll_if_running(initial, stdin_tool)

    result, final = asyncio.run(run())

    assert "hello" in result
    assert "Exit code: 0" in final
    assert "session_id:" not in final


def test_exec_session_yield_returns_when_process_finishes_early(tmp_path):
    async def run() -> str:
        manager = ExecSessionManager()
        tool = ExecTool(working_dir=str(tmp_path), timeout=20, session_manager=manager)
        ready, release = tmp_path / "ready", tmp_path / "release"
        command = python_command(
            "from pathlib import Path\nimport time\n"
            "Path('ready').write_text('ready')\n"
            "while not Path('release').exists(): time.sleep(0.01)\n"
            "print('done')"
        )
        pending = asyncio.create_task(tool.execute(command=command, yield_time_ms=15000))
        try:
            async with asyncio.timeout(10):
                while not ready.exists():
                    if pending.done():
                        pytest.fail(f"child exited before readiness: {await pending}")
                    await asyncio.sleep(0.01)
            # Measure responsiveness only after the actual child is ready to exit.
            release.touch()
            return await asyncio.wait_for(pending, timeout=3)
        finally:
            release.touch()
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            await manager.close_all()

    result = asyncio.run(run())

    assert "done" in result
    assert "Exit code: 0" in result
    assert "session_id:" not in result


def test_exec_one_shot_accepts_max_output_tokens_alias(tmp_path):
    async def run() -> str:
        tool = ExecTool(working_dir=str(tmp_path), timeout=5)
        command = python_command("print('A' * 2000)")
        return await tool.execute(command=command, max_output_tokens=1000, yield_time_ms=10000)

    result = asyncio.run(run())

    assert "chars truncated" in result
    assert "Exit code: 0" in result


def test_exec_accepts_supported_shell_parameter(tmp_path):
    async def run() -> str:
        tool = ExecTool(working_dir=str(tmp_path), timeout=5)
        return await tool.execute(command="echo shell-ok", shell="sh", login=False)

    if sys.platform == "win32":
        return
    result = asyncio.run(run())

    assert "shell-ok" in result
    assert "Exit code: 0" in result


def test_exec_rejects_unsupported_shell(tmp_path):
    async def run() -> str:
        tool = ExecTool(working_dir=str(tmp_path), timeout=5)
        return await tool.execute(command="echo no", shell="python")

    if sys.platform == "win32":
        return
    result = asyncio.run(run())

    assert "unsupported shell" in result


def test_exec_session_mode_reuses_exec_safety_guard(tmp_path):
    manager = ExecSessionManager()
    tool = ExecTool(
        working_dir=str(tmp_path),
        deny_patterns=[r"echo\s+blocked"],
        restrict_to_workspace=True,
        session_manager=manager,
    )

    result = asyncio.run(tool.execute(command="echo blocked", yield_time_ms=0))

    assert "blocked by deny pattern" in result


def test_exec_session_reports_missing_session(tmp_path):
    manager = ExecSessionManager()
    tool = ExecSessionTool(manager=manager)

    result = asyncio.run(tool.execute(session_id="missing\nExit code: 0", input=""))

    assert result == "Error: exec session not found: 'missing\\nExit code: 0'"
    assert is_tool_error_result(result)


def test_list_exec_sessions_reports_running_commands(tmp_path):
    async def run() -> tuple[str, str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        list_tool = ListExecSessionsTool(manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = waiting_shell_command("ready")

        initial = await exec_tool.execute(command=command, yield_time_ms=500)
        sid = extract_session_id(initial)
        listing = await list_tool.execute()
        cleanup = await stdin_tool.execute(session_id=sid, terminate=True)
        return sid, listing, cleanup

    sid, listing, cleanup = asyncio.run(run())

    assert sid in listing
    assert "running" in listing
    assert "elapsed=" in listing
    assert "remaining=" in listing
    assert str(tmp_path) in listing
    assert "Session terminated." in cleanup


def test_exec_sessions_are_scoped_to_request_session_key(tmp_path):
    async def run() -> tuple[str, str, str, str, str, str]:
        manager = ExecSessionManager()
        exec_tool = ExecTool(working_dir=str(tmp_path), timeout=5, session_manager=manager)
        list_tool = ListExecSessionsTool(manager=manager)
        stdin_tool = ExecSessionTool(manager=manager)
        command = python_command(
            "import time; print('ready', flush=True); time.sleep(5)"
        )

        token_a = bind_request_context(
            RequestContext(channel="cli", chat_id="a", session_key="cli:a")
        )
        try:
            initial = await exec_tool.execute(command=command, yield_time_ms=100)
            sid = extract_session_id(initial)
            owner_listing = await list_tool.execute()
        finally:
            reset_request_context(token_a)

        unbound_listing = await list_tool.execute()

        token_b = bind_request_context(
            RequestContext(channel="cli", chat_id="b", session_key="cli:b")
        )
        try:
            other_listing = await list_tool.execute()
            other_write = await stdin_tool.execute(session_id=sid, timeout_ms=0)
        finally:
            reset_request_context(token_b)

        token_a = bind_request_context(
            RequestContext(channel="cli", chat_id="a", session_key="cli:a")
        )
        try:
            cleanup = await stdin_tool.execute(session_id=sid, terminate=True)
        finally:
            reset_request_context(token_a)

        return sid, owner_listing, unbound_listing, other_listing, other_write, cleanup

    sid, owner_listing, unbound_listing, other_listing, other_write, cleanup = asyncio.run(run())

    assert sid in owner_listing
    assert unbound_listing == "No active exec sessions."
    assert other_listing == "No active exec sessions."
    assert other_write == f"Error: exec session not found: {sid!r}"
    assert "Session terminated." in cleanup


def test_list_exec_sessions_reports_empty_state():
    result = asyncio.run(ListExecSessionsTool(manager=ExecSessionManager()).execute())

    assert result == "No active exec sessions."
