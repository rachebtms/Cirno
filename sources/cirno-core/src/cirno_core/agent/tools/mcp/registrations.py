"""MCP server ownership of registered capabilities."""

from __future__ import annotations

from cirno_core.agent.tools.base import Tool
from cirno_core.agent.tools.mcp.names import _tool_prefix
from cirno_core.agent.tools.mcp.wrappers import _MCPWrapperBase
from cirno_core.agent.tools.registry import ToolRegistry


def _tool_belongs_to_server(tool: Tool | None, tool_name: str, server_name: str) -> bool:
    if isinstance(tool, _MCPWrapperBase):
        return getattr(tool, "_server_name", None) == server_name
    return tool_name.startswith(_tool_prefix(server_name))


def _unregister_server_tools(registry: ToolRegistry, server_name: str) -> int:
    removed = 0
    for tool_name in list(registry.tool_names):
        tool = registry.get(tool_name)
        if _tool_belongs_to_server(tool, tool_name, server_name):
            registry.unregister(tool_name)
            removed += 1
    return removed
