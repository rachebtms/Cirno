"""Persist validated custom connections and OAuth setup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cirno_core.agent.tools.mcp_oauth import (
    delete_mcp_oauth_credentials,
)
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.contracts import (
    McpPresetError,
    QueryParams,
    preset_by_name_optional,
    query_first,
    query_value,
    validated_server_name,
)
from cirno_server.webui.mcp.fields import (
    clone_server,
    materialize_server,
    proxy_enabled,
    validate_proxy,
)
from cirno_server.webui.mcp.messages import server_action_message
from cirno_server.webui.mcp.parsing import (
    custom_server_from_query,
    import_mcp_servers,
    parse_enabled_tools,
)


def _oauth_credentials_replaced(
    previous: MCPServerConfig | None,
    replacement: MCPServerConfig,
) -> bool:
    if previous is None or previous.auth != "oauth":
        return False
    return replacement.auth != "oauth" or replacement.url != previous.url


def custom_mcp_action(
    action: str,
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = load_config(config_path) if config_path is not None else load_config()
    if action == "custom":
        name, cfg = custom_server_from_query(query)
        validate_proxy(cfg, config.network)
        delete_credentials = _oauth_credentials_replaced(config.tools.mcp_servers.get(name), cfg)
        config.tools.mcp_servers[name] = cfg
        save_config(config, config_path)
        if delete_credentials:
            delete_mcp_oauth_credentials(name)
        payload = mcp_presets_payload(
            last_action=server_action_message(action, name),
            config_path=config_path,
        )
        payload["requires_restart"] = True
        return payload

    if action in {"import", "import-cursor"}:
        servers = import_mcp_servers(query_first(query, "config"))
        for cfg in servers.values():
            validate_proxy(cfg, config.network)
        delete_credentials = [
            name
            for name, cfg in servers.items()
            if _oauth_credentials_replaced(config.tools.mcp_servers.get(name), cfg)
        ]
        config.tools.mcp_servers.update(servers)
        save_config(config, config_path)
        for name in delete_credentials:
            delete_mcp_oauth_credentials(name)
        payload = mcp_presets_payload(
            last_action={
                "ok": True,
                "message": f"Imported {len(servers)} MCP server(s).",
            },
            config_path=config_path,
        )
        payload["requires_restart"] = True
        return payload

    if action == "tools":
        name = validated_server_name((query_first(query, "name") or "").strip())
        cfg = config.tools.mcp_servers.get(name)
        if cfg is None:
            raise McpPresetError("unknown MCP server", status=404)
        cfg.enabled_tools = parse_enabled_tools(query_first(query, "enabled_tools"))
        config.tools.mcp_servers[name] = cfg
        save_config(config, config_path)
        payload = mcp_presets_payload(
            last_action=server_action_message(action, name),
            config_path=config_path,
        )
        payload["requires_restart"] = True
        return payload

    raise McpPresetError(f"unknown MCP action '{action}'", status=404)


def ensure_mcp_oauth_server(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> tuple[str, MCPServerConfig, NetworkConfig]:
    """Materialize an OAuth preset on first click and return its saved config."""
    name = validated_server_name((query_first(query, "name") or "").strip())
    config = load_config(config_path) if config_path is not None else load_config()
    cfg = config.tools.mcp_servers.get(name)
    preset = preset_by_name_optional(name)
    fields_provided = preset is not None and any(
        query_value(query, field.name) for field in preset.fields
    )
    if cfg is None or fields_provided:
        if preset is None:
            raise McpPresetError("unknown MCP preset", status=404)
        if preset.server is None or preset.server.auth != "oauth":
            raise McpPresetError("MCP server does not support browser authorization", status=409)
        cfg = materialize_server(preset, query, cfg)
    cfg = clone_server(cfg)
    cfg.use_proxy = proxy_enabled(query, cfg.use_proxy)
    validate_proxy(cfg, config.network)
    if cfg.auth != "oauth" or cfg.type not in {"sse", "streamableHttp"} or not cfg.url:
        raise McpPresetError("MCP server is not configured for OAuth", status=409)
    config.tools.mcp_servers[name] = cfg
    save_config(config, config_path)
    return name, cfg, config.network
