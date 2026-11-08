"""Filtered child environments and configured command search paths."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from cirno_core.processes import platform
from cirno_core.utils.tool_environment import TOOL_ENV_KEYS


@dataclass(slots=True)
class ExecutionEnvironment:
    path_prepend: str = ""
    path_append: str = ""
    allowed_env_keys: list[str] = field(default_factory=list)

    def build(self) -> dict[str, str]:
        """Build a minimal environment for subprocess execution.

        Preserve standard tool paths and configuration locations, including the
        configured Bash startup file. Credentials require explicit allowed keys.

        On Windows, ``cmd.exe`` has no login-profile mechanism, so a curated
        set of system variables (including PATH) is forwarded.  API keys and
        other secrets are still excluded.
        """
        if platform.IS_WINDOWS:
            sr = os.environ.get("SYSTEMROOT", r"C:\Windows")
            env = {
                "SYSTEMROOT": sr,
                "COMSPEC": os.environ.get("COMSPEC", f"{sr}\\system32\\cmd.exe"),
                "USERPROFILE": os.environ.get("USERPROFILE", ""),
                "HOMEDRIVE": os.environ.get("HOMEDRIVE", "C:"),
                "HOMEPATH": os.environ.get("HOMEPATH", "\\"),
                "TEMP": os.environ.get("TEMP", f"{sr}\\Temp"),
                "TMP": os.environ.get("TMP", f"{sr}\\Temp"),
                "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
                "PATH": os.environ.get("PATH", f"{sr}\\system32;{sr}"),
                "PYTHONUNBUFFERED": "1",
                "APPDATA": os.environ.get("APPDATA", ""),
                "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
                "ProgramData": os.environ.get("ProgramData", ""),
                "ProgramFiles": os.environ.get("ProgramFiles", ""),
                "ProgramFiles(x86)": os.environ.get("ProgramFiles(x86)", ""),
                "ProgramW6432": os.environ.get("ProgramW6432", ""),
            }
            for key in (*TOOL_ENV_KEYS, *self.allowed_env_keys):
                val = os.environ.get(key)
                if val is not None:
                    env[key] = val
            return env
        home = os.environ.get("HOME", "/tmp")
        env = {
            "HOME": home,
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TERM": os.environ.get("TERM", "dumb"),
            "PYTHONUNBUFFERED": "1",
        }
        for key in (*TOOL_ENV_KEYS, *self.allowed_env_keys):
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        return env

    def compose_path(self, current_path: str) -> str:
        parts: list[str] = []
        if self.path_prepend:
            parts.append(self.path_prepend)
        if current_path:
            parts.append(current_path)
        if self.path_append:
            parts.append(self.path_append)
        return os.pathsep.join(parts)

    def wrap_path_export(self, command: str, env: dict[str, str]) -> str:
        segments: list[str] = []
        if self.path_prepend:
            env["CIRNO_PATH_PREPEND"] = self.path_prepend
            segments.append("$CIRNO_PATH_PREPEND")
        segments.append("$PATH")
        if self.path_append:
            env["CIRNO_PATH_APPEND"] = self.path_append
            segments.append("$CIRNO_PATH_APPEND")
        path_expr = os.pathsep.join(segments)
        return f'export PATH="{path_expr}"; {command}'
