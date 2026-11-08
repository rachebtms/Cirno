"""Describe preset, custom and plugin MCP capabilities for the catalog."""

from __future__ import annotations

import urllib.parse
from typing import Any

from cirno_core.agent.plugins import (
    AgentPlugin,
)
from cirno_core.apps.protocol import app_manifest, compact_dict
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.presets import McpPreset


def connection_summary(cfg: MCPServerConfig | None) -> str:
    if cfg is None:
        return ""
    if cfg.command:
        return " ".join([cfg.command, *cfg.args[:2]]).strip()
    if cfg.url:
        parsed = urllib.parse.urlsplit(cfg.url)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return ""


def tool_allowlist(cfg: MCPServerConfig | None) -> list[str]:
    if cfg is None:
        return ["*"]
    return list(cfg.enabled_tools)


def _managed_mcp_path(name: str, cfg: MCPServerConfig | None) -> list[str]:
    if cfg is None or not cfg.command:
        return []
    return [f"runtime:mcp/{name}"]


def preset_manifest(preset: McpPreset, *, logo_url: str) -> dict[str, Any]:
    server = preset.server
    managed_paths = _managed_mcp_path(preset.name, server)
    field_specs = [
        compact_dict(
            {
                "name": field.name,
                "target": field.target[0],
                "required": field.required,
                "secret": field.secret,
                "env_var": field.env_var,
            }
        )
        for field in preset.fields
    ]
    capabilities = [
        compact_dict(
            {
                "type": "mcp",
                "transport": preset.transport,
                "auth": server.auth if server and server.auth else None,
                "command": server.command if server and server.command else None,
                "args": list(server.args) if server and server.command else None,
                "url": connection_summary(server) if server and server.url else None,
                "fields": field_specs,
            }
        )
    ]
    return app_manifest(
        app_id=preset.name,
        display_name=preset.display_name,
        description=preset.description,
        category=preset.category,
        source="mcp-preset",
        docs_url=preset.docs_url,
        logo_url=logo_url,
        brand_color=preset.brand_color,
        capabilities=capabilities,
        install=compact_dict(
            {
                "supported": preset.install_supported,
                "strategy": "config",
                "managed_paths": managed_paths,
                "verification": ["config_present", "dependency_available"],
            }
        ),
        remove=compact_dict(
            {
                "supported": True,
                "strategy": "config",
                "managed_paths": managed_paths,
                "verification": ["config_absent", "managed_paths_absent"]
                if managed_paths
                else ["config_absent"],
            }
        ),
        trust={
            "registry": "mcp-presets",
            "level": "builtin",
            "review_status": "builtin_preset",
        },
    )


def custom_manifest(name: str, cfg: MCPServerConfig) -> dict[str, Any]:
    transport = cfg.type or ("stdio" if cfg.command else "streamableHttp")
    managed_paths: list[str] = []
    return app_manifest(
        app_id=name,
        display_name=name,
        description="Custom MCP server from cirno config.",
        category="custom",
        source="mcp-custom",
        brand_color="#64748B",
        capabilities=[
            compact_dict(
                {
                    "type": "mcp",
                    "transport": transport,
                    "auth": cfg.auth,
                    "command": cfg.command or None,
                    "url": connection_summary(cfg) if cfg.url else None,
                }
            )
        ],
        install=compact_dict(
            {
                "supported": True,
                "strategy": "config",
                "managed_paths": managed_paths,
                "verification": ["config_present", "dependency_available"],
            }
        ),
        remove=compact_dict(
            {
                "supported": True,
                "strategy": "config",
                "managed_paths": managed_paths,
                "verification": ["config_absent", "managed_paths_absent"]
                if managed_paths
                else ["config_absent"],
            }
        ),
        trust={
            "registry": "user-config",
            "level": "user",
            "review_status": "user_managed",
        },
    )


def agent_plugin_payload(plugin: AgentPlugin) -> dict[str, Any]:
    return {
        "name": f"plugin-{plugin.name}",
        "display_name": plugin.display_name,
        "category": plugin.category,
        "description": plugin.description or "Agent Plugin",
        "docs_url": plugin.repository,
        "transport": "stdio",
        "requires": ", ".join(plugin.permissions),
        "note": "",
        "install_supported": False,
        "installed": True,
        "configured": True,
        "enabled": plugin.enabled,
        "available": plugin.enabled,
        "status": "enabled" if plugin.enabled else "disabled",
        "logo_url": plugin.logo,
        "brand_color": plugin.accent_color,
        "required_fields": [],
        "connection_summary": ", ".join(plugin.mcp_servers),
        "source": "agent-plugin",
    }
