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
from cirno_core.config.loader import get_config_path, load_config, save_config
from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import WebUISettingsConfig

from cirno_server.webui.mcp.catalog import attach_mcp_runtime_status, mcp_presets_payload
from cirno_server.webui.mcp.cleanup import active_server_names
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
from cirno_server.webui.mcp.messages import (
    action_message,
    record_cleanup_failure,
    server_action_message,
)

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
            cfg = materialize_server(preset, query, None, config_path=config.source_path)
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
        cfg = materialize_server(preset, query, existing, config_path=config.source_path)
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
        validated_server_name(name)
        if "cleanup_only" in query:
            if (query_first(query, "cleanup_only") or "").lower() != "true":
                raise McpPresetError("cleanup_only must be true")
        if "cleanup_only" in query or name not in config.tools.mcp_servers:
            live = active_server_names(config, discover_agent_plugins(config.workspace_path, config_path=config.source_path))
            if name.casefold() in {item.casefold() for item in live}:
                raise McpPresetError("MCP server is configured again; cleanup was not performed", status=409)
        removed_runtime_files = False
        cleanup_error = False
        credential_cleanup_error = False
        existing_cfg = config.tools.mcp_servers.pop(name, None)
        if existing_cfg is not None:
            # Config persistence is the commit boundary. Never destroy runtime
            # data while a failed save would leave its connection configured.
            save_config(config, config_path)
        try:
            removed_runtime_files = remove_managed_stdio_cwd(name, existing_cfg, config_path=config.source_path)
        except (OSError, McpPresetError) as exc:
            cleanup_error = True
            logger.warning("MCP runtime cleanup failed for '{}' ({})", name, type(exc).__name__)
        try:
            delete_mcp_oauth_credentials(name, config_path=config.source_path)
        except OSError as exc:
            credential_cleanup_error = True
            logger.warning("MCP credential cleanup failed for '{}' ({})", name, type(exc).__name__)
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
            record_cleanup_failure(last_action, name=name, verification="managed_paths_absent")
        if credential_cleanup_error:
            record_cleanup_failure(last_action, name=name, verification=f"oauth_credentials_absent:{name}")
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


def _plugin_settings_action(action: str, name: str, config_path: Path | None) -> dict[str, Any] | None:
    """Classify and commit a plugin mutation while holding its config owner lock."""
    plugin_config = load_config(config_path) if config_path is not None else load_config()
    if name in plugin_config.tools.mcp_servers:
        return None
    plugin_name = name.removeprefix("plugin-")
    plugins = discover_agent_plugins(plugin_config.workspace_path, config_path=plugin_config.source_path)
    plugin = next((item for item in plugins if item.name == plugin_name), None)
    if plugin is None:
        return None
    if action not in {"enable", "disable"}:
        raise McpPresetError("Agent Plugins support enable and disable actions only")
    set_agent_plugin_enabled(
        plugin_config.workspace_path, plugin_name, action == "enable", config_path=plugin_config.source_path,
    )
    verb = "enabled" if action == "enable" else "disabled"
    payload = mcp_presets_payload(
        last_action={"ok": True, "message": f"{plugin.display_name} {verb}."},
        config_path=plugin_config.source_path,
    )
    payload["requires_restart"] = True
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
        selected_path = config_path if config_path is not None else get_config_path()
        payload = await shield_and_drain(asyncio.to_thread(
            mcp_presets_payload, config_path=selected_path,
        ))
        # Runtime state can advance while filesystem discovery is in flight.
        # Observe it on its owning loop immediately before publishing the rows.
        runtime_status = dict(mcp_runtime_status()) if mcp_runtime_status is not None else None
        return attach_mcp_runtime_status(payload, runtime_status)
    name = (query_first(query, "name") or "").strip()
    if name.startswith("plugin-") and "cleanup_only" not in query:
        if config is not None:
            payload = await asyncio.to_thread(
                config.run_serialized,
                lambda path: _plugin_settings_action(action, name, path),
            )
        else:
            payload = await asyncio.to_thread(
                _plugin_settings_action, action, name, config_path,
            )
        if payload is not None:
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
