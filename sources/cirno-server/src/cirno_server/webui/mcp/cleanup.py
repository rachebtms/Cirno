"""Discover removed MCP leftovers from existing instance stores."""

from collections.abc import Iterable

from cirno_core.agent.plugins import AgentPlugin
from cirno_core.agent.tools.mcp_oauth import mcp_oauth_stored_server_names
from cirno_core.config.schema import Config
from loguru import logger

from cirno_server.webui.mcp.contracts import MCP_SERVER_NAME_RE, McpPresetError
from cirno_server.webui.mcp.fields import _managed_stdio_root


def active_server_names(config: Config, plugins: Iterable[AgentPlugin]) -> set[str]:
    names = set(config.tools.mcp_servers)
    for plugin in plugins:
        if plugin.enabled:
            # Match agent_plugin_mcp_servers' runtime identities, not catalog row IDs.
            names.update(
                plugin.name if len(plugin.mcp_servers) == 1 else f"{plugin.name}--{name}"
                for name in plugin.mcp_servers
            )
    return names


def pending_cleanup_names(config: Config, plugins: Iterable[AgentPlugin]) -> list[str]:
    """Rediscover leftovers after refresh/restart; no new persistence root or job."""
    active = {name.casefold() for name in active_server_names(config, plugins)}
    candidates: set[str] = set()
    try:
        root = _managed_stdio_root(config.source_path)
        if root.exists():
            candidates.update(
                entry.name
                for entry in root.iterdir()
                if entry.is_symlink() or entry.is_dir() or entry.is_file()
            )
    except (OSError, McpPresetError) as exc:
        logger.warning("Could not inspect MCP runtime leftovers ({})", type(exc).__name__)
    try:
        candidates.update(mcp_oauth_stored_server_names(config_path=config.source_path))
    except OSError as exc:
        logger.warning("Could not inspect MCP credential leftovers ({})", type(exc).__name__)
    return sorted(
        name
        for name in candidates
        if MCP_SERVER_NAME_RE.fullmatch(name) and name.casefold() not in active
    )
