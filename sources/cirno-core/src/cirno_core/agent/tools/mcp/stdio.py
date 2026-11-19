"""MCP stdio."""

from __future__ import annotations

import os
import shutil

_WINDOWS_SHELL_LAUNCHERS: frozenset[str] = frozenset(("npx", "npm", "pnpm", "yarn", "bunx"))


def locate_stdio_command(
    command: str, *, cwd: str | None = None, env: dict[str, str] | None = None,
) -> str | None:
    """Locate a command in its child cwd/PATH without executing it."""
    if not command:
        return None
    directory = os.path.abspath(cwd or os.getcwd())
    if not os.path.isdir(directory):
        return None
    inherited_path = os.environ.get("PATH", os.defpath)
    # Match the SDK's safe default-environment inheritance.
    search_path = os.defpath if inherited_path.startswith("()") else inherited_path
    for key, value in (env or {}).items():
        if key == "PATH" or os.name == "nt" and key.upper() == "PATH":
            search_path = value
    search_path = os.pathsep.join(
        os.path.abspath(os.path.join(directory, entry))
        for entry in search_path.split(os.pathsep)
    )
    candidate = os.path.join(directory, command) if os.path.dirname(command) else command
    resolved = shutil.which(candidate, path=search_path)
    return os.path.abspath(resolved) if resolved is not None else None


def _windows_command_basename(command: str) -> str:
    """Return the lowercase basename for a Windows command or path."""
    return command.replace("\\", "/").rsplit("/", maxsplit=1)[-1].lower()


def _normalize_windows_stdio_command(
    command: str,
    args: list[str] | None,
    env: dict[str, str] | None,
) -> tuple[str, list[str], dict[str, str] | None]:
    """Wrap Windows shell launchers so MCP stdio servers start reliably."""
    normalized_args = list(args or [])
    if os.name != "nt":
        return command, normalized_args, env

    basename = _windows_command_basename(command)
    if basename in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return command, normalized_args, env

    if basename.endswith((".exe", ".com")):
        return command, normalized_args, env

    resolved = shutil.which(command, path=(env or {}).get("PATH")) or command
    resolved_basename = _windows_command_basename(resolved)
    should_wrap = (
        basename in _WINDOWS_SHELL_LAUNCHERS
        or basename.endswith((".cmd", ".bat"))
        or resolved_basename.endswith((".cmd", ".bat"))
    )
    if not should_wrap:
        return command, normalized_args, env

    comspec = (env or {}).get("COMSPEC") or os.environ.get("COMSPEC") or "cmd.exe"
    return comspec, ["/d", "/c", command, *normalized_args], env
