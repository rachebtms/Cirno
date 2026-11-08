"""Dispatch MCP settings operations through configuration and runtime owners."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cirno_core.agent.plugins import (
    discover_agent_plugins,
    set_agent_plugin_enabled,
)
from cirno_core.agent.tools.mcp_oauth import (
    delete_mcp_oauth_credentials,
)
from cirno_core.config.loader import load_config, save_config

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import WebUISettingsConfig

from cirno_server.webui.mcp.catalog import attach_mcp_runtime_status, mcp_presets_payload
from cirno_server.webui.mcp.configuration import custom_mcp_action
from cirno_server.webui.mcp.contracts import (
    McpPresetError,
    McpReload,
    McpRuntimeStatus,
    QueryParams,
    preset_by_name_optional,
    query_first,
    validated_server_name,
)
from cirno_server.webui.mcp.fields import (
    clone_server,
    materialize_server,
    proxy_enabled,
    remove_managed_stdio_cwd,
    validate_proxy,
)
from cirno_server.webui.mcp.messages import action_message, server_action_message

_CUSTOM_ACTIONS = {"custom", "import", "import-cursor", "tools"}


def mcp_reconnect_action(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Validate a configured server before asking the live runtime to retry it."""
    name = validated_server_name((query_first(query, "name") or "").strip())
    config = load_config(config_path) if config_path is not None else load_config()
    if name not in config.tools.mcp_servers:
        raise McpPresetError("unknown MCP server", status=404)
    payload = mcp_presets_payload(
        last_action=server_action_message("reconnect", name),
        config_path=config_path,
    )
    payload["requires_restart"] = True
    return payload


def mcp_presets_action(
    action: str,
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    name = (query_first(query, "name") or "").strip()
    if not name:
        raise McpPresetError("missing MCP preset name")
    preset = preset_by_name_optional(name)

    config = load_config(config_path) if config_path is not None else load_config()
    existing = config.tools.mcp_servers.get(name)

    if action == "proxy":
        if existing is None:
            if preset is None:
                raise McpPresetError("unknown MCP server", status=404)
            cfg = materialize_server(preset, query, None)
        else:
            cfg = clone_server(existing)
            cfg.use_proxy = proxy_enabled(query, cfg.use_proxy)
        validate_proxy(cfg, config.network)
        config.tools.mcp_servers[name] = cfg
        save_config(config, config_path)
        payload = mcp_presets_payload(config_path=config_path)
        payload["requires_restart"] = True
        return payload

    if action == "enable":
        if preset is None:
            raise McpPresetError("unknown MCP preset", status=404)
        cfg = materialize_server(preset, query, existing)
        validate_proxy(cfg, config.network)
        config.tools.mcp_servers[preset.name] = cfg
        save_config(config, config_path)
        payload = mcp_presets_payload(
            last_action=action_message(action, preset),
            config_path=config_path,
        )
        payload["requires_restart"] = True
        return payload

    if action == "remove":
        if preset is None and name not in config.tools.mcp_servers:
            raise McpPresetError("unknown MCP server", status=404)
        removed_runtime_files = False
        cleanup_error = ""
        if name in config.tools.mcp_servers:
            existing_cfg = config.tools.mcp_servers[name]
            try:
                removed_runtime_files = remove_managed_stdio_cwd(name, existing_cfg)
            except OSError as exc:
                cleanup_error = str(exc)
            del config.tools.mcp_servers[name]
            save_config(config, config_path)
            delete_mcp_oauth_credentials(name)
        last_action = (
            action_message(action, preset)
            if preset is not None
            else server_action_message(action, name)
        )
        if removed_runtime_files:
            last_action["message"] = f"{last_action['message']} Removed managed runtime files."
            last_action["managed_paths_removed"] = [f"runtime:mcp/{name}"]
            last_action["verification"] = ["config_absent", "managed_paths_absent"]
        if cleanup_error:
            last_action["ok"] = False
            last_action["message"] = (
                f"{last_action['message']} Could not remove managed runtime files: {cleanup_error}"
            )
            last_action["verification_failed"] = ["managed_paths_absent"]
        payload = mcp_presets_payload(
            last_action=last_action,
            config_path=config_path,
        )
        payload["requires_restart"] = True
        return payload

    if action == "test":
        raise McpPresetError("MCP preset test must run through the async test action", status=500)

    raise McpPresetError(f"unknown MCP preset action '{action}'", status=404)


def attach_mcp_hot_reload_result(
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Merge an agent MCP reload acknowledgement into a WebUI settings payload."""
    payload = dict(payload)
    payload["hot_reload"] = result
    payload["requires_restart"] = bool(result.get("requires_restart"))
    last_action = dict(payload.get("last_action") or {})
    base_message = str(last_action.get("message") or "").strip()
    reload_message = str(result.get("message") or "").strip()
    if reload_message:
        last_action["message"] = (
            f"{base_message} {reload_message}" if base_message else reload_message
        )
    if "ok" not in last_action:
        last_action["ok"] = bool(result.get("ok", False))
    payload["last_action"] = last_action
    return payload


async def mcp_presets_settings_action(
    action: str | None,
    query: QueryParams,
    *,
    reload_mcp: McpReload | None = None,
    mcp_runtime_status: McpRuntimeStatus | None = None,
    config: WebUISettingsConfig | None = None,
) -> dict[str, Any]:
    """Run a WebUI MCP preset action and hot-reload the agent when config changes."""
    config_path = config.path if config is not None else None
    if action is None:
        return mcp_presets_payload(
            runtime_status=mcp_runtime_status() if mcp_runtime_status is not None else None,
            config_path=config_path,
        )
    name = (query_first(query, "name") or "").strip()
    if name.startswith("plugin-"):
        plugin_config = load_config(config_path) if config_path is not None else load_config()
        plugin_name = name.removeprefix("plugin-")
        plugins = discover_agent_plugins(plugin_config.workspace_path)
        plugin = next((item for item in plugins if item.name == plugin_name), None)
        if name not in plugin_config.tools.mcp_servers and plugin is not None:
            if action not in {"enable", "disable"}:
                raise McpPresetError("Agent Plugins support enable and disable actions only")
            await asyncio.to_thread(
                set_agent_plugin_enabled,
                plugin_config.workspace_path,
                plugin_name,
                action == "enable",
            )
            verb = "enabled" if action == "enable" else "disabled"
            payload = mcp_presets_payload(
                last_action={"ok": True, "message": f"{plugin.display_name} {verb}."},
                config_path=config_path,
            )
            if reload_mcp is not None:
                payload = attach_mcp_hot_reload_result(payload, await reload_mcp())
            return payload
    if action == "test":
        from cirno_server.webui.mcp.inspection import mcp_presets_test_action

        payload = await mcp_presets_test_action(query, config_path=config_path)
        return attach_mcp_runtime_status(
            payload,
            mcp_runtime_status() if mcp_runtime_status is not None else None,
        )
    if action == "reconnect":
        payload = await asyncio.to_thread(
            mcp_reconnect_action,
            query,
            config_path=config_path,
        )
    elif config is not None:
        operation = custom_mcp_action if action in _CUSTOM_ACTIONS else mcp_presets_action
        payload = await asyncio.to_thread(
            config.run_serialized,
            lambda path: operation(action, query, config_path=path),
        )
    elif action in _CUSTOM_ACTIONS:
        payload = await asyncio.to_thread(custom_mcp_action, action, query)
    else:
        payload = await asyncio.to_thread(mcp_presets_action, action, query)
    if reload_mcp is not None:
        payload = attach_mcp_hot_reload_result(payload, await reload_mcp())
    return attach_mcp_runtime_status(
        payload,
        mcp_runtime_status() if mcp_runtime_status is not None else None,
    )
