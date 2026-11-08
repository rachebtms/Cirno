"""Launch shell strings or native argument vectors with owned process trees."""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path, PureWindowsPath

from cirno_core.processes import lifecycle, platform
from cirno_core.processes.lifecycle import PROCESS_TREE_OWNER_ATTR
from cirno_core.processes.shells import normalize_powershell_command


async def spawn_process(
    command: str | list[str],
    cwd: str,
    env: dict[str, str],
    shell_program: str | None = None,
    login: bool = False,
    *,
    stdin: int = asyncio.subprocess.DEVNULL,
    process_tree: bool = False,
) -> asyncio.subprocess.Process:
    """Launch an argument vector directly or a command string through a shell."""
    if isinstance(command, list):
        executable = shutil.which(command[0], path=env.get("PATH", ""))
        if executable is None:
            raise FileNotFoundError(f"Executable not found: {command[0]}")
        windows_job = None
        process = None
        try:
            if process_tree and sys.platform == "win32":
                windows_job = lifecycle.create_windows_job()
            process = await asyncio.create_subprocess_exec(
                executable,
                *command[1:],
                stdin=stdin,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                creationflags=windows_job.creation_flags if windows_job else 0,
                start_new_session=process_tree and sys.platform != "win32",
            )
            if windows_job is not None:
                windows_job.assign_and_resume(process.pid)
                setattr(process, PROCESS_TREE_OWNER_ATTR, windows_job)
            return process
        except BaseException:
            if windows_job is not None:
                windows_job.terminate()
            if process is not None:
                await lifecycle.kill_process(process)
            raise
    if platform.IS_WINDOWS:
        windows_job = None
        process = None
        creation_flags = 0
        if process_tree and sys.platform == "win32":
            windows_job = lifecycle.create_windows_job()
            creation_flags = windows_job.creation_flags
        # Default to PowerShell so single-line and multi-line commands
        # share the same shell semantics.  cmd.exe is reachable via the
        # explicit shell="cmd" parameter (see _resolve_shell).
        default_program = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        program = shell_program or default_program
        program_name = PureWindowsPath(program).name.lower()
        try:
            if program_name in ("cmd", "cmd.exe"):
                cmd_env = {**env, "COMSPEC": program}
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdin=stdin,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=cmd_env,
                    creationflags=creation_flags,
                )
            else:
                command = normalize_powershell_command(command)
                command = (
                    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
                    "if ($PSVersionTable.PSVersion.Major -lt 6) { $OutputEncoding = [Console]::OutputEncoding }\n"
                    "$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'\n"
                    f"{command}\n"
                    "if ($LASTEXITCODE -ne $null) { exit $LASTEXITCODE }"
                )
                process = await asyncio.create_subprocess_exec(
                    program,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    command,
                    stdin=stdin,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    env=env,
                    creationflags=creation_flags,
                )
            if windows_job is not None:
                windows_job.assign_and_resume(process.pid)
                setattr(process, PROCESS_TREE_OWNER_ATTR, windows_job)
            return process
        except BaseException:
            if windows_job is not None:
                windows_job.terminate()
            if process is not None:
                await lifecycle.kill_process(process)
            raise
    shell_program = shell_program or shutil.which("bash") or "/bin/bash"
    args: list[str] = [shell_program]
    shell_name = Path(shell_program).name.lower()
    if login and shell_name in {"bash", "bash.exe", "zsh", "zsh.exe"}:
        args.append("-l")
    args.extend(["-c", command])
    if process_tree:
        return await asyncio.create_subprocess_exec(
            *args,
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
    return await asyncio.create_subprocess_exec(
        *args,
        stdin=stdin,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
