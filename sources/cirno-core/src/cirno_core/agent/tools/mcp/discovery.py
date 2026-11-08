"""Discover paginated MCP capabilities and register allowed tool adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal

from cirno_core.agent.tools.mcp.names import _sanitize_mcp_tool_name
from cirno_core.agent.tools.mcp.wrappers import MCPPromptWrapper, MCPResourceWrapper, MCPToolWrapper
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.tools.base import Tool
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.config.tools import MCPServerConfig
    from mcp import ClientSession
    from mcp.types import ServerCapabilities


async def list_catalog(
    request: Callable[..., Awaitable[Any]],
    kind: Literal["tools", "resources", "prompts"],
) -> list[Any]:
    """Fetch a complete catalog before any of its adapters become available."""
    from mcp.types import PaginatedRequestParams

    page = await request()
    entries = list(getattr(page, kind))
    seen: set[str] = set()
    while page.nextCursor is not None:
        cursor = page.nextCursor
        if cursor in seen:
            raise ValueError(f"MCP {kind}/list returned a repeated pagination cursor")
        seen.add(cursor)
        page = await request(params=PaginatedRequestParams(cursor=cursor))
        entries.extend(getattr(page, kind))
    return entries


async def optional_catalog(
    request: Callable[..., Awaitable[Any]],
    kind: Literal["resources", "prompts"],
    server_name: str,
) -> list[Any]:
    from mcp.shared.exceptions import McpError

    try:
        return await list_catalog(request, kind)
    except McpError as exc:
        if exc.error.code == -32601:
            logger.debug("MCP server '{}': {} not supported", server_name, kind)
            return []
        logger.warning(
            "MCP server '{}': {}/list failed (code {})",
            server_name,
            kind,
            exc.error.code,
        )
    except Exception as exc:
        logger.warning(
            "MCP server '{}': {}/list failed ({})",
            server_name,
            kind,
            type(exc).__name__,
        )
    return []


async def register_capabilities(
    session: ClientSession,
    capabilities: ServerCapabilities,
    name: str,
    cfg: MCPServerConfig,
    registry: ToolRegistry,
) -> int:
    definitions = (
        await list_catalog(session.list_tools, "tools") if capabilities.tools is not None else []
    )
    enabled = set(cfg.enabled_tools)
    allow_all = "*" in enabled
    matched: set[str] = set()
    adapters: list[Tool] = []
    available_names = [_sanitize_mcp_tool_name(f"mcp_{name}_{item.name}") for item in definitions]
    for definition, wrapped_name in zip(definitions, available_names, strict=True):
        if not allow_all and definition.name not in enabled and wrapped_name not in enabled:
            continue
        wrapper = MCPToolWrapper(session, name, definition, tool_timeout=cfg.tool_timeout)
        adapters.append(wrapper)
        matched.update({definition.name, wrapped_name} & enabled)
        logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)
    if not allow_all and (missing := sorted(enabled - matched)):
        logger.warning(
            "MCP server '{}': enabledTools entries not found: {}. Available raw names: {}. "
            "Available wrapped names: {}",
            name,
            ", ".join(missing),
            ", ".join(item.name for item in definitions) or "(none)",
            ", ".join(available_names) or "(none)",
        )
    # Resource and prompt adapters are unavailable when the operator restricts tools.
    if not allow_all:
        return commit_adapters(adapters, registry)
    if capabilities.resources is not None:
        for resource in await optional_catalog(session.list_resources, "resources", name):
            adapters.append(
                MCPResourceWrapper(session, name, resource, resource_timeout=cfg.tool_timeout)
            )
    if capabilities.prompts is not None:
        for prompt in await optional_catalog(session.list_prompts, "prompts", name):
            adapters.append(
                MCPPromptWrapper(session, name, prompt, prompt_timeout=cfg.tool_timeout)
            )
    return commit_adapters(adapters, registry)


def commit_adapters(adapters: list[Tool], registry: ToolRegistry) -> int:
    names = set(registry.tool_names)
    for adapter in adapters:
        if adapter.name in names:
            raise ValueError(f"MCP capabilities have a duplicate model-facing name: {adapter.name}")
        names.add(adapter.name)
    for adapter in adapters:
        registry.register(adapter)
    return len(adapters)
