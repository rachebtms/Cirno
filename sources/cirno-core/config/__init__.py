"""Configuration module for cirno."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cirno.config.errors import ConfigIssue, ConfigLoadError
    from cirno.config.loader import get_config_path, load_config
    from cirno.config.paths import (
        get_cron_dir,
        get_data_dir,
        get_logs_dir,
        get_media_dir,
        get_runtime_subdir,
        get_webui_dir,
        get_workspace_path,
        is_default_workspace,
    )
    from cirno.config.schema import Config


_EXPORTS = {
    "Config": "cirno.config.schema",
    "ConfigIssue": "cirno.config.errors",
    "ConfigLoadError": "cirno.config.errors",
    "load_config": "cirno.config.loader",
    "get_config_path": "cirno.config.loader",
    "get_data_dir": "cirno.config.paths",
    "get_runtime_subdir": "cirno.config.paths",
    "get_media_dir": "cirno.config.paths",
    "get_cron_dir": "cirno.config.paths",
    "get_logs_dir": "cirno.config.paths",
    "get_webui_dir": "cirno.config.paths",
    "get_workspace_path": "cirno.config.paths",
    "is_default_workspace": "cirno.config.paths",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "Config",
    "ConfigIssue",
    "ConfigLoadError",
    "load_config",
    "get_config_path",
    "get_data_dir",
    "get_runtime_subdir",
    "get_media_dir",
    "get_cron_dir",
    "get_logs_dir",
    "get_webui_dir",
    "get_workspace_path",
    "is_default_workspace",
]
