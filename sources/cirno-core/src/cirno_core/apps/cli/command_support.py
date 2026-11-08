"""Parse package commands and discover installed distributions."""

from __future__ import annotations

import shlex
import shutil
import sys
from importlib import metadata as importlib_metadata
from typing import Any, cast

_SHELL_META_CHARS = ("|", "&&", "||", ";", "$(", "`", ">", "<")


def _has_shell_meta(command: str) -> bool:
    return any(char in command for char in _SHELL_META_CHARS)


def _command_exists(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    return shutil.which(parts[0]) is not None


def _is_pip_install_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return (len(tokens) >= 3 and tokens[:2] == ["pip", "install"]) or (
        len(tokens) >= 5
        and tokens[1:4] == ["-m", "pip", "install"]
        and tokens[0] in {"python", "python3", sys.executable}
    )


def _pip_uninstall_args_from_command(command: str) -> list[str] | None:
    if not command or _has_shell_meta(command):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if tokens[:2] == ["pip", "uninstall"]:
        args = tokens[2:]
    elif (
        len(tokens) >= 5
        and tokens[1:4] == ["-m", "pip", "uninstall"]
        and tokens[0] in {"python", "python3", sys.executable}
    ):
        args = tokens[4:]
    else:
        return None
    packages = [arg for arg in args if arg not in {"-y", "--yes"}]
    if not packages or any(arg.startswith("-") for arg in packages):
        return None
    return packages


def _console_script_distribution(entry_point: str) -> str | None:
    if not entry_point:
        return None
    try:
        distributions = importlib_metadata.distributions()
    except Exception:
        return None
    for distribution in distributions:
        try:
            entry_points = distribution.entry_points
        except Exception:
            continue
        for item in entry_points:
            if item.group != "console_scripts" or item.name != entry_point:
                continue
            try:
                name: object = cast(Any, distribution.metadata).get("Name")
            except Exception:
                name = None
            fallback_name = cast(object, getattr(distribution, "name", ""))
            return str(name or fallback_name or "").strip() or None
    return None
