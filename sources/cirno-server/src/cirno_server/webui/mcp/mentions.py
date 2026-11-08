"""Resolve structured MCP mentions against the configured catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from cirno_core.config.loader import load_config
from cirno_server.webui.mcp.contracts import MCP_SERVER_NAME_RE, known_preset_names

_MCP_ATTACHMENT_KEYS = (
    "name",
    "display_name",
    "category",
    "transport",
    "logo_url",
    "brand_color",
    "status",
    "configured",
)


def _known_mcp_names(config_path: Path | None = None) -> set[str]:
    names = known_preset_names()
    names.update(load_config(config_path).tools.mcp_servers)
    return names


def _clip_ws_string(value: Any, limit: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def normalize_mcp_preset_mentions(
    raw: Any,
    *,
    config_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Sanitize structured MCP preset mentions sent by the WebUI."""
    if not isinstance(raw, list):
        return []
    known = _known_mcp_names(config_path)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item_value in cast(list[object], raw)[:8]:
        if not isinstance(item_value, dict):
            continue
        item = cast(dict[str, Any], item_value)
        name = _clip_ws_string(item.get("name"), 64)
        if not name or MCP_SERVER_NAME_RE.match(name) is None:
            continue
        key = name.lower()
        if key in seen or key not in known:
            continue
        seen.add(key)
        row: dict[str, Any] = {"name": key}
        for field_name in _MCP_ATTACHMENT_KEYS[1:]:
            value = item.get(field_name)
            if isinstance(value, bool):
                row[field_name] = value
                continue
            limit = 512 if field_name == "logo_url" else 160
            text = _clip_ws_string(value, limit)
            if text:
                row[field_name] = text
        out.append(row)
    return out
