"""Shared uv commands for service, Agent and standalone setup environments."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal


def package_command(
    action: Literal["install", "uninstall"],
    python: str | Path,
    arguments: Sequence[str],
) -> list[str]:
    aliases = {"--force-reinstall": "--reinstall", "--no-cache-dir": "--no-cache"}
    return ["uv", "pip", action, "--python", str(python), *(aliases.get(arg, arg) for arg in arguments)]


def environment(values: Mapping[str, str]) -> dict[str, str]:
    result = dict(values)
    for pip_name, uv_name in (("PIP_INDEX_URL", "UV_INDEX_URL"),
                             ("PIP_EXTRA_INDEX_URL", "UV_EXTRA_INDEX_URL"),
                             ("PIP_FIND_LINKS", "UV_FIND_LINKS")):
        if value := result.get(pip_name):
            result.setdefault(uv_name, value)
    return result


def venv_command(python: str | Path, destination: Path) -> list[str]:
    return ["uv", "venv", "--no-project", "--allow-existing", "--python", str(python), str(destination)]
