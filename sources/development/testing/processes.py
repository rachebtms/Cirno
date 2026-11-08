"""Subprocess fixtures and deterministic observation helpers."""

from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace

from cirno_core.agent.tools.exec_session import ExecSessionTool
from cirno_core.processes.sessions.session import ExecSession


def python_command(code: str) -> str:
    if sys.platform == "win32":
        return (
            f"{subprocess.list2cmdline([sys.executable])} -u -c {subprocess.list2cmdline([code])}"
        )
    return f"{shlex.quote(sys.executable)} -u -c {shlex.quote(code)}"


def waiting_shell_command(initial: str, *, delayed: str | None = None) -> str:
    """Print deterministic output, optionally gated by stdin, then keep waiting.

    Long-lived Python children keep inherited pipes open after their parent
    shell is terminated on Windows. These tests exercise exec-session control,
    not process-tree semantics, so keep the waiter in the managed shell.
    """
    if sys.platform == "win32":

        def quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        parts = [f"Write-Output {quote(initial)}"]
        if delayed is not None:
            parts.extend(("$null = [Console]::In.ReadLine()", f"Write-Output {quote(delayed)}"))
        parts.append("$null = [Console]::In.ReadLine()")
        return "; ".join(parts)

    parts = [f"printf '%s\\n' {shlex.quote(initial)}"]
    if delayed is not None:
        parts.extend(("IFS= read -r _", f"printf '%s\\n' {shlex.quote(delayed)}"))
    parts.append("IFS= read -r _")
    return "; ".join(parts)


def extract_session_id(output: str) -> str:
    match = re.search(r"session_id:\s*([0-9a-f]+)", output)
    assert match, output
    return match.group(1)


def fake_session_process(
    *,
    stdout: asyncio.StreamReader | None = None,
    stderr: asyncio.StreamReader | None = None,
) -> tuple[SimpleNamespace, asyncio.Event]:
    exited = asyncio.Event()
    process = SimpleNamespace(pid=12345, stdout=stdout, stderr=stderr, returncode=None)

    async def wait() -> int:
        await exited.wait()
        assert process.returncode is not None
        return process.returncode

    process.wait = wait
    return process, exited


async def cancel_session_tasks(session: ExecSession) -> None:
    tasks = [session._stdout_task, session._stderr_task, session._completion_task]
    tasks.extend(task for task in (session._timeout_task, session._kill_task) if task is not None)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def poll_if_running(
    initial: str,
    tool: ExecSessionTool,
    *,
    timeout_ms: int = 2000,
) -> tuple[str, str]:
    if "session_id:" not in initial:
        return initial, initial
    final = await tool.execute(
        session_id=extract_session_id(initial),
        until_exit=True,
        timeout_ms=timeout_ms,
    )
    return f"{initial}\n{final}", final
