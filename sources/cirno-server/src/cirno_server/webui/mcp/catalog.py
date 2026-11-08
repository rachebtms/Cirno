"""Project configured MCP connections into settings and chat catalog rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, cast

from cirno_core.agent.plugins import (
    discover_agent_plugins,
)
from cirno_core.agent.tools.mcp_oauth import (
    mcp_oauth_has_credentials,
)
from cirno_core.config.loader import load_config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.contracts import (
    McpPresetError,
    favicon_url,
    known_preset_names,
    validated_server_name,
)
from cirno_server.webui.mcp.fields import (
    command_available,
    config_available,
    field_payload,
    status_for,
)
from cirno_server.webui.mcp.manifests import (
    agent_plugin_payload,
    connection_summary,
    custom_manifest,
    preset_manifest,
    tool_allowlist,
)
from cirno_server.webui.mcp.presets import MCP_PRESETS, McpPreset

_MCP_RUNTIME_STATUSES = {"connecting", "connected", "failed"}


def _preset_payload(
    preset: McpPreset, configured_servers: dict[str, MCPServerConfig]
) -> dict[str, Any]:
    cfg = configured_servers.get(preset.name)
    status = status_for(preset, cfg)
    configured = cfg is not None and status not in {"missing_credentials", "authorization_required"}
    logo_url = favicon_url(preset.brand_domain)
    return {
        "name": preset.name,
        "display_name": preset.display_name,
        "category": preset.category,
        "description": preset.description,
        "docs_url": preset.docs_url,
        "transport": preset.transport,
        "auth": (cfg.auth if cfg is not None else (preset.server.auth if preset.server else None)),
        "use_proxy": cfg.use_proxy if cfg is not None else False,
        "requires": preset.requires,
        "note": preset.note,
        "install_supported": preset.install_supported,
        "installed": cfg is not None,
        "configured": configured,
        "available": configured and config_available(cfg),
        "status": status,
        "logo_url": logo_url,
        "brand_color": preset.brand_color,
        "required_fields": [field_payload(field, cfg) for field in preset.fields],
        "connection_summary": connection_summary(cfg),
        "enabled_tools": tool_allowlist(cfg),
        "source": "preset",
        "manifest": preset_manifest(preset, logo_url=logo_url),
    }


def custom_mcp_config_payload(name: str, *, config_path: Path | None = None) -> dict[str, Any]:
    """Read one custom server for the authenticated configuration editor."""
    name = validated_server_name(name)
    config = load_config(config_path)
    if name in known_preset_names() or name not in config.tools.mcp_servers:
        raise McpPresetError("unknown custom MCP server", status=404)
    return {"config": config.tools.mcp_servers[name].model_dump(mode="json", by_alias=True)}


def _custom_payload(
    name: str,
    cfg: MCPServerConfig,
    *,
    tool_names: list[str] | None = None,
) -> dict[str, Any]:
    transport = cfg.type
    if not transport:
        transport = (
            "stdio"
            if cfg.command
            else ("sse" if cfg.url.rstrip("/").endswith("/sse") else "streamableHttp")
        )
    if cfg.auth == "oauth" and not mcp_oauth_has_credentials(name, cfg.url):
        status = "authorization_required"
    else:
        status = (
            "missing_dependency"
            if cfg.command and not command_available(cfg.command)
            else "configured"
        )
    configured = status != "authorization_required"
    return {
        "name": name,
        "display_name": name,
        "category": "custom",
        "description": "Custom MCP server from cirno config.",
        "docs_url": "",
        "transport": transport,
        "auth": cfg.auth,
        "use_proxy": cfg.use_proxy,
        "requires": "",
        "note": "",
        "install_supported": True,
        "installed": True,
        "configured": configured,
        "available": configured and config_available(cfg),
        "status": status,
        "logo_url": None,
        "brand_color": "#64748B",
        "required_fields": [],
        "connection_summary": connection_summary(cfg),
        "enabled_tools": tool_allowlist(cfg),
        "tool_names": tool_names or [],
        "source": "custom",
        "manifest": custom_manifest(name, cfg),
    }


def mcp_presets_payload(
    *,
    last_action: dict[str, Any] | None = None,
    tool_preview: Mapping[str, list[str]] | None = None,
    runtime_status: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = load_config(config_path) if config_path is not None else load_config()
    known = known_preset_names()
    preset_rows = [
        _preset_payload(preset, config.tools.mcp_servers)
        | (
            {"tool_names": tool_preview.get(preset.name, [])}
            if tool_preview and preset.name in tool_preview
            else {}
        )
        for preset in MCP_PRESETS
    ]
    custom_rows = [
        _custom_payload(name, cfg, tool_names=(tool_preview or {}).get(name))
        for name, cfg in sorted(config.tools.mcp_servers.items())
        if name not in known
    ]
    existing_names = {str(row["name"]) for row in (*preset_rows, *custom_rows)}
    plugin_rows = [
        agent_plugin_payload(plugin)
        for plugin in discover_agent_plugins(config.workspace_path)
        if f"plugin-{plugin.name}" not in existing_names
    ]
    payload: dict[str, Any] = {
        "presets": [*preset_rows, *custom_rows, *plugin_rows],
        "proxy_configured": bool(config.network.proxy),
        "installed_count": len(config.tools.mcp_servers)
        + sum(int(row["enabled"]) for row in plugin_rows),
    }
    if last_action is not None:
        payload["last_action"] = last_action
    return attach_mcp_runtime_status(payload, runtime_status)


def attach_mcp_runtime_status(
    payload: dict[str, Any],
    runtime_status: Mapping[str, str] | None,
) -> dict[str, Any]:
    """Project safe, connection-attempt state onto eligible installed MCP rows."""
    if runtime_status is None:
        return payload
    projected = dict(payload)
    raw_rows: object = payload.get("presets", [])
    preset_rows = cast(list[object], raw_rows) if isinstance(raw_rows, list) else []
    rows: list[Any] = []
    for raw_row in preset_rows:
        if not isinstance(raw_row, dict):
            rows.append(raw_row)
            continue
        row = dict(cast(dict[str, Any], raw_row))
        name = row.get("name")
        status = runtime_status.get(name) if isinstance(name, str) else None
        oauth_authorization_failed = (
            status == "failed"
            and row.get("auth") == "oauth"
            and row.get("status") == "authorization_required"
        )
        if (
            status in _MCP_RUNTIME_STATUSES
            and row.get("installed") is True
            and (row.get("configured") is True or oauth_authorization_failed)
        ):
            row["runtime_status"] = status
        else:
            row.pop("runtime_status", None)
        rows.append(row)
    projected["presets"] = rows
    return projected
