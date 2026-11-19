"""MCP provider."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from cirno_core.agent.tools.base import Tool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.network import NetworkConfig
from cirno_core.utils.cancellation import shield_and_drain, task_is_cancelling

if TYPE_CHECKING:
    from cirno_core.config.schema import Config
    from cirno_core.config.tools import MCPServerConfig

from cirno_core.agent.tools.mcp.connections import close_mcp_connections
from cirno_core.agent.tools.mcp.connector import connect_mcp_servers
from cirno_core.agent.tools.mcp.contracts import MCPConnection, MCPRuntimeStatus, MCPServerLoader
from cirno_core.agent.tools.mcp.registrations import (
    _tool_belongs_to_server,
    _unregister_server_tools,
)
from cirno_core.agent.tools.mcp.wrappers import _MCPWrapperBase


def session_extra(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return persisted session kwargs for MCP preset attachments."""
    mcp_presets = metadata.get("mcp_presets") if isinstance(metadata, Mapping) else None
    return {"mcp_presets": mcp_presets} if isinstance(mcp_presets, list) and mcp_presets else {}


def _configured_servers(config: Config) -> dict[str, MCPServerConfig]:
    from cirno_core.agent.plugins import agent_plugin_mcp_servers

    return agent_plugin_mcp_servers(
        config.workspace_path,
        config.tools.mcp_servers,
        config_path=config.source_path,
    )


def _load_current_servers(config_path: Path | None = None) -> tuple[dict[str, MCPServerConfig], NetworkConfig]:
    from cirno_core.config.loader import load_config, resolve_config_env_vars

    config = resolve_config_env_vars(load_config(config_path), config_path=config_path)
    return _configured_servers(config), config.network


@dataclass(frozen=True)
class _ReloadPreparation:
    servers: dict[str, MCPServerConfig]
    added: list[str]
    removed: list[str]
    changed: list[str]
    authorization_pending: set[str]
    tools_removed: int


class MCPProvider:
    """Own configured MCP connections and their dynamic tool registrations."""

    def __init__(
        self,
        servers: Mapping[str, MCPServerConfig],
        registry: ToolRegistry,
        *,
        server_loader: MCPServerLoader | None = None,
        network: NetworkConfig | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._servers = dict(servers)
        self._network = (network or NetworkConfig()).model_copy(deep=True)
        self._config_path = config_path.expanduser().resolve(strict=False) if config_path is not None else None
        self._registry = registry
        self._server_loader = server_loader or _load_current_servers
        self._connections: dict[str, MCPConnection] = {}
        self._runtime_statuses: dict[str, MCPRuntimeStatus] = {}
        self._lock = asyncio.Lock()
        self._closing = False

    @classmethod
    def from_config(
        cls,
        config: Config,
        registry: ToolRegistry,
        *,
        server_loader: MCPServerLoader | None = None,
    ) -> MCPProvider:
        if server_loader is None and config.source_path is not None:
            server_loader = partial(_load_current_servers, config.source_path)
        return cls(
            _configured_servers(config),
            registry,
            server_loader=server_loader,
            network=config.network,
            config_path=config.source_path,
        )

    def _has_oauth_credentials(self, name: str, url: str) -> bool:
        from cirno_core.agent.tools.mcp_oauth import mcp_oauth_has_credentials

        if self._config_path is None:
            return mcp_oauth_has_credentials(name, url)
        return mcp_oauth_has_credentials(name, url, config_path=self._config_path)

    def _pending_authorizations(self, servers: Mapping[str, MCPServerConfig]) -> set[str]:
        return {
            name for name, cfg in servers.items()
            if cfg.auth == "oauth" and not self._has_oauth_credentials(name, cfg.url)
        }

    def _read_reload_snapshot(self) -> tuple[dict[str, MCPServerConfig], NetworkConfig, set[str]]:
        servers, network = self._server_loader()
        snapshot = dict(servers)
        return snapshot, network, self._pending_authorizations(snapshot)

    async def _prepare_reload(self) -> _ReloadPreparation:
        next_servers, next_network, authorization_pending = await asyncio.to_thread(self._read_reload_snapshot)
        current_names = set(self._servers)
        next_names = set(next_servers)
        removed = sorted(current_names - next_names)
        added = sorted(next_names - current_names)
        changed = sorted(
            name for name in current_names & next_names
            if _server_signature(self._servers[name]) != _server_signature(next_servers[name])
            or (next_servers[name].use_proxy and self._network.proxy != next_network.proxy)
        )
        # Keep accepted loader side effects, snapshot publication and old-connection
        # cleanup owned together. Cancellation must never start new connections.
        self._servers = next_servers
        self._network = next_network.model_copy(deep=True)
        tools_removed = await self._retire_servers(set(removed) | set(changed) | authorization_pending)
        return _ReloadPreparation(next_servers, added, removed, changed, authorization_pending, tools_removed)

    async def _connect_servers(self, servers: dict[str, MCPServerConfig]) -> dict[str, MCPConnection]:
        if self._config_path is None:
            return await connect_mcp_servers(servers, self._registry, network=self._network)
        return await connect_mcp_servers(servers, self._registry, network=self._network, config_path=self._config_path)

    @property
    def configured_server_names(self) -> set[str]:
        return set(self._servers)

    @property
    def connected_server_names(self) -> set[str]:
        return set(self._connections)

    def runtime_status(self) -> dict[str, MCPRuntimeStatus]:
        """Return the latest connection-attempt result for configured servers."""
        return {
            name: status for name, status in self._runtime_statuses.items() if name in self._servers
        }

    def _set_runtime_status(
        self,
        server_names: Iterable[str],
        status: MCPRuntimeStatus,
    ) -> None:
        for name in server_names:
            self._runtime_statuses[name] = status

    def _record_connection_result(
        self,
        attempted: Iterable[str],
        connected: Iterable[str],
    ) -> None:
        attempted_names = set(attempted)
        connected_names = set(connected)
        self._set_runtime_status(connected_names, "connected")
        self._set_runtime_status(attempted_names - connected_names, "failed")

    async def connect(self) -> None:
        """Connect configured servers that are not currently live."""
        async with self._lock:
            if self._closing:
                return
            configured_missing = {
                name: cfg for name, cfg in self._servers.items() if name not in self._connections
            }
            oauth_servers = {
                name: cfg for name, cfg in self._servers.items() if cfg.auth == "oauth"
            }
            authorization_pending: set[str] = set()
            if oauth_servers:
                authorization_pending = await asyncio.to_thread(self._pending_authorizations, oauth_servers)
            await self._retire_servers(authorization_pending)
            if self._closing:
                return
            missing_servers = {
                name: cfg
                for name, cfg in configured_missing.items()
                if name not in authorization_pending
            }
            if not missing_servers:
                return
            self._set_runtime_status(missing_servers, "connecting")
            try:
                connected = await self._connect_servers(missing_servers)
                if self._closing:
                    await close_mcp_connections(connected)
                    return
                self._connections.update(connected)
                self._record_connection_result(missing_servers, connected)
                self._attach_reconnect_handlers(connected)
                if connected:
                    logger.info("MCP connected servers: {}", sorted(connected))
                else:
                    logger.warning(
                        "No MCP servers connected successfully "
                        "(will retry on the next readiness check)"
                    )
            except asyncio.CancelledError:
                self._set_runtime_status(missing_servers, "failed")
                if task_is_cancelling():
                    raise
                logger.warning("MCP connection cancelled (will retry on the next readiness check)")
            except Exception as exc:
                self._set_runtime_status(missing_servers, "failed")
                logger.warning(
                    "Failed to connect MCP servers (will retry on the next readiness check): {}",
                    type(exc).__name__,
                )

    async def reload(self) -> dict[str, Any]:
        """Reconcile live MCP connections with the current configuration."""
        async with self._lock:
            if self._closing:
                return self._closing_result()
            try:
                preparation = await shield_and_drain(self._prepare_reload())
            except Exception as exc:
                logger.warning("MCP hot reload could not read config: {}", exc)
                return {
                    "ok": False,
                    "message": "Could not reload MCP config. Restart cirno to pick up changes.",
                    "requires_restart": True,
                    "error": str(exc),
                }

            if self._closing:
                return self._closing_result()
            next_servers = preparation.servers
            next_names = set(next_servers)
            added, removed, changed = preparation.added, preparation.removed, preparation.changed
            authorization_pending = preparation.authorization_pending
            tools_removed = preparation.tools_removed
            retry_missing = sorted(
                name
                for name in next_names
                if name not in self._connections
                and name not in set(added) | set(changed)
                and name not in authorization_pending
            )
            to_connect_names = sorted(
                (set(added) | set(changed) | set(retry_missing)) - authorization_pending
            )
            to_connect = {name: next_servers[name] for name in to_connect_names}
            connected: dict[str, MCPConnection] = {}
            if to_connect:
                self._set_runtime_status(to_connect, "connecting")
                try:
                    connected = await self._connect_servers(to_connect)
                except BaseException:
                    self._set_runtime_status(to_connect, "failed")
                    raise
                if self._closing:
                    await close_mcp_connections(connected)
                    return self._closing_result()
                self._connections.update(connected)
                self._record_connection_result(to_connect, connected)
                self._attach_reconnect_handlers(connected)

            failed = sorted(set(to_connect) - set(connected))
            unchanged = not removed and not added and not changed and not retry_missing
            ok = not failed
            if failed:
                message = "MCP config reloaded, but some servers did not connect: " + ", ".join(
                    failed
                )
            elif authorization_pending:
                message = "MCP browser authorization is required for: " + ", ".join(sorted(authorization_pending))
            elif unchanged:
                message = "MCP config is already live."
            elif retry_missing and not added and not changed and not removed:
                message = "MCP connections refreshed without restarting cirno."
            else:
                message = "MCP config reloaded without restarting cirno."

            logger.info(
                "MCP hot reload: added={} changed={} removed={} retried={} "
                "connected={} failed={} tools_removed={}",
                added,
                changed,
                removed,
                retry_missing,
                sorted(connected),
                failed,
                tools_removed,
            )
            return {
                "ok": ok,
                "message": message,
                "added": added,
                "changed": changed,
                "removed": removed,
                "retried": retry_missing,
                "connected": sorted(self._connections),
                "configured": sorted(self._servers),
                "failed": failed,
                "authorization_required": sorted(authorization_pending),
                "tools_removed": tools_removed,
                "requires_restart": False,
            }

    @staticmethod
    def _closing_result() -> dict[str, Any]:
        return {
            "ok": False,
            "message": "MCP connections are shutting down.",
            "requires_restart": True,
        }

    def _attach_reconnect_handlers(self, server_names: Iterable[str]) -> None:
        async def reconnect(
            server_name: str,
            tool_name: str,
            stale_tool: Tool,
        ) -> Tool | None:
            return await self._refresh_terminated_server(
                server_name,
                tool_name,
                stale_tool,
            )

        for server_name in server_names:
            for tool_name in list(self._registry.tool_names):
                tool = self._registry.get(tool_name)
                if not _tool_belongs_to_server(tool, tool_name, server_name):
                    continue
                if isinstance(tool, _MCPWrapperBase):
                    tool.set_reconnect_handler(reconnect)

    async def _refresh_terminated_server(
        self,
        server_name: str,
        tool_name: str,
        stale_tool: Tool,
    ) -> Tool | None:
        async with self._lock:
            if self._closing:
                return None
            cfg = self._servers.get(server_name)
            if cfg is None:
                logger.warning(
                    "MCP server '{}' session terminated but is no longer configured",
                    server_name,
                )
                return None

            if cfg.auth == "oauth":
                authorized = await asyncio.to_thread(self._has_oauth_credentials, server_name, cfg.url)
                if self._closing:
                    return None
                if not authorized:
                    await self._retire_servers({server_name})
                    logger.info("MCP server '{}' is waiting for browser authorization", server_name)
                    return None

            current_tool = self._registry.get(tool_name)
            if (
                current_tool is not None
                and current_tool is not stale_tool
                and server_name in self._connections
            ):
                return current_tool

            logger.warning(
                "MCP server '{}' session terminated; refreshing connection",
                server_name,
            )
            await self._retire_servers({server_name})
            if self._closing:
                return None

            self._set_runtime_status({server_name}, "connecting")
            connected = await self._connect_servers({server_name: cfg})
            if self._closing:
                await close_mcp_connections(connected)
                return None
            self._connections.update(connected)
            self._record_connection_result({server_name}, connected)
            self._attach_reconnect_handlers(connected)
            if server_name not in connected:
                logger.warning(
                    "MCP server '{}' reconnect failed after session termination",
                    server_name,
                )
                return None
            return self._registry.get(tool_name)

    async def _retire_servers(self, server_names: Iterable[str]) -> int:
        """Withdraw the whole obsolete capability set before draining any close."""
        connections: dict[str, MCPConnection] = {}
        removed = 0
        for name in sorted(set(server_names)):
            removed += _unregister_server_tools(self._registry, name)
            self._runtime_statuses.pop(name, None)
            connection = self._connections.pop(name, None)
            if connection is not None:
                connections[name] = connection
        await close_mcp_connections(connections)
        return removed

    async def aclose(self) -> None:
        """Close every connection while excluding reconnect and hot reload."""
        self._closing = True
        async with self._lock:
            connections = dict(self._connections)
            self._connections.clear()
            self._runtime_statuses.clear()
            for name in self._servers:
                _unregister_server_tools(self._registry, name)
            await close_mcp_connections(connections)


def _server_signature(cfg: Any) -> Any:
    if hasattr(cfg, "model_dump"):
        return cfg.model_dump(mode="json")
    return cfg
