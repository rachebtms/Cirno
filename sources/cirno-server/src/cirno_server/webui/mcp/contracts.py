"""MCP server identities, query contracts and owner-facing errors."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any, Mapping

from cirno_server.webui.mcp.presets import MCP_PRESETS, McpPreset

QueryParams = dict[str, list[str]]


MCP_SERVER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)


McpReload = Callable[[], Awaitable[dict[str, Any]]]


McpRuntimeStatus = Callable[[], Mapping[str, str]]


class McpPresetError(Exception):
    """WebUI-facing MCP preset error."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def favicon_url(domain: str) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def query_first(query: QueryParams, key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def query_value(query: QueryParams, key: str) -> str | None:
    raw = query_first(query, key)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _preset_by_name(name: str) -> McpPreset:
    if not name or MCP_SERVER_NAME_RE.match(name) is None:
        raise McpPresetError("invalid MCP preset name")
    for preset in MCP_PRESETS:
        if preset.name == name:
            return preset
    raise McpPresetError("unknown MCP preset", status=404)


def preset_by_name_optional(name: str) -> McpPreset | None:
    try:
        return _preset_by_name(name)
    except McpPresetError:
        return None


def known_preset_names() -> set[str]:
    return {preset.name for preset in MCP_PRESETS}


def display_name_for(name: str, preset: McpPreset | None = None) -> str:
    return preset.display_name if preset is not None else name


def validated_server_name(name: str) -> str:
    if not name or MCP_SERVER_NAME_RE.match(name) is None:
        raise McpPresetError("invalid MCP server name")
    return name.strip().lower()
