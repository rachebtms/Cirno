"""CLI Apps helpers for the WebUI HTTP and message surfaces."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cirno_core.apps.cli import CliAppError, CliAppManager, CliAppsRuntimeConfig
from cirno_core.config.loader import load_config
from cirno_core.runtime.admission import RuntimeMaintenanceError

QueryParams = dict[str, list[str]]

_CLI_APP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_CLI_APP_ATTACHMENT_KEYS = (
    "name",
    "display_name",
    "category",
    "entry_point",
    "logo_url",
    "brand_color",
)
def _clip_ws_string(value: Any, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def normalize_cli_app_mentions(raw: Any) -> list[dict[str, str]]:
    """Sanitize structured CLI app mentions sent by the WebUI."""
    if not isinstance(raw, list):
        return []
    raw_items = cast(list[Any], raw)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items[:8]:
        if not isinstance(item, dict):
            continue
        app_data = cast(dict[str, Any], item)
        name = _clip_ws_string(app_data.get("name"), 64)
        if not name or _CLI_APP_NAME_RE.match(name) is None:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, str] = {"name": key}
        for field in _CLI_APP_ATTACHMENT_KEYS[1:]:
            value = _clip_ws_string(
                app_data.get(field),
                512 if field == "logo_url" else 160,
            )
            if value:
                row[field] = value
        out.append(row)
    return out


def _query_first(query: QueryParams, key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _manager(config_path: Path | None = None) -> CliAppManager:
    config = load_config(config_path) if config_path is not None else load_config()
    cli_cfg = config.tools.cli_apps
    return CliAppManager(
        workspace=config.workspace_path,
        runtime=CliAppsRuntimeConfig(
            install_timeout=cli_cfg.install_timeout,
            run_timeout=cli_cfg.run_timeout,
            catalog_ttl_seconds=cli_cfg.catalog_ttl_seconds,
        ),
    )


@dataclass(frozen=True, slots=True)
class _LocalRead:
    payload: dict[str, Any]
    refresh_manager: CliAppManager | None = None


def _read_local(*, installed_only: bool, config_path: Path | None) -> _LocalRead:
    manager = _manager(config_path) if config_path is not None else _manager()
    if installed_only:
        return _LocalRead(manager.installed_payload())
    payload = manager.payload(cache_only=True)
    refresh_manager = None if manager.registry.catalog_cache_fresh(include_optional=True) else manager
    if not payload["apps"]:
        installed = manager.installed_payload()
        if installed["apps"]:
            payload = installed
    return _LocalRead(payload, refresh_manager)


async def cli_apps_payload(
    *,
    installed_only: bool = False,
    config_path: Path | None = None,
    start_refresh: Callable[[CliAppManager], bool] | None = None,
) -> dict[str, Any]:
    """Read local state; detached refresh requires an explicit runtime owner."""
    # Configuration, cache reads and executable discovery can all block on disk.
    local = await asyncio.to_thread(_read_local, installed_only=installed_only, config_path=config_path)
    if not installed_only:
        # Refresh task/throttle state belongs to this event loop, not the reader.
        try:
            pending = (
                start_refresh(local.refresh_manager)
                if start_refresh is not None and local.refresh_manager is not None else False
            )
        except RuntimeMaintenanceError:
            # Maintenance can start while a read-only snapshot is in flight.
            # Serve the snapshot without admitting a new cache writer.
            pending = False
        local.payload["catalog_refresh_pending"] = pending
    return local.payload


def cli_apps_action(
    action: str,
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    name = (_query_first(query, "name") or "").strip()
    if not name:
        raise CliAppError("missing CLI app name")
    manager = _manager(config_path) if config_path is not None else _manager()
    if action == "install":
        return manager.install(name)
    if action == "update":
        return manager.update(name)
    if action == "uninstall":
        return manager.uninstall(name)
    if action == "test":
        return manager.test(name)
    raise CliAppError(f"unknown CLI app action '{action}'", status=404)
