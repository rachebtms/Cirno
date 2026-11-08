"""Supported shell selection and PowerShell invocation syntax."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from cirno_core.processes import platform


def normalize_powershell_command(command: str) -> str:
    stripped = command.lstrip()
    if not stripped or stripped[0] not in {"'", '"'}:
        return command

    quote = stripped[0]
    end = stripped.find(quote, 1)
    if end == -1 or (end + 1 < len(stripped) and not stripped[end + 1].isspace()):
        return command

    executable = stripped[1:end]
    looks_like_windows_executable = (
        bool(re.match(r"^[A-Za-z]:[\\/]", executable))
        or executable.startswith(r"\\")
        or executable.lower().endswith((".exe", ".cmd", ".bat", ".ps1"))
    )
    if not looks_like_windows_executable:
        return command

    leading = command[: len(command) - len(stripped)]
    return f"{leading}& {stripped}"


def resolve_shell(shell: str | None) -> str | None:
    if not shell:
        return None
    if "\0" in shell or "\n" in shell or "\r" in shell:
        raise ValueError("shell contains invalid characters")
    if platform.IS_WINDOWS:
        win_allowed = {"powershell", "powershell.exe", "pwsh", "pwsh.exe", "cmd", "cmd.exe"}
        path = Path(shell).expanduser()
        if path.is_absolute():
            name = path.name.lower()
            if name not in win_allowed:
                raise ValueError(f"unsupported shell {shell!r}. Allowed: powershell, pwsh, cmd")
            if not path.is_file():
                raise ValueError(f"shell is not found: {shell}")
            return str(path)
        if "/" in shell or "\\" in shell:
            raise ValueError("shell must be a shell name or absolute path")
        if shell.lower() not in win_allowed:
            raise ValueError(f"unsupported shell {shell!r}. Allowed: powershell, pwsh, cmd")
        if shell.lower() in ("cmd", "cmd.exe"):
            resolved = os.environ.get("COMSPEC") or shutil.which("cmd") or "cmd"
            return resolved
        resolved = shutil.which(shell) or shell
        return resolved
    allowed = {"sh", "bash", "zsh"}
    path = Path(shell).expanduser()
    if path.is_absolute():
        if path.name not in allowed:
            raise ValueError(f"unsupported shell {shell!r}. Allowed: bash, sh, zsh")
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"shell is not executable: {shell}")
        return str(path)
    if "/" in shell or "\\" in shell:
        raise ValueError("shell must be a shell name or absolute path")
    if shell not in allowed:
        raise ValueError(f"unsupported shell {shell!r}. Allowed: bash, sh, zsh")
    resolved = shutil.which(shell)
    if not resolved:
        raise ValueError(f"shell not found: {shell}")
    return resolved
