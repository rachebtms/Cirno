"""Capture MCP presentation identity without changing tool schemas or model input."""

from cirno_core.agent.tools.mcp.wrappers import _MCPWrapperBase
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.providers.tool_calls import ToolCallRequest


def mcp_tool_activity(tools: ToolRegistry, calls: list[ToolCallRequest]) -> dict[str, dict[str, str]]:
    identities: dict[str, dict[str, str]] = {}
    for call in calls:
        tool = tools.get(call.name)
        if isinstance(tool, _MCPWrapperBase):
            identities[call.id] = tool.activity_identity
    return identities
