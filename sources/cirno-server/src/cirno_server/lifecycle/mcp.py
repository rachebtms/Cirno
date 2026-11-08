"""Prepare application-owned MCP capabilities before a model turn starts."""

from cirno_core.agent.hook import AgentHook, AgentRunHookContext
from cirno_core.agent.tools.mcp.provider import MCPProvider


class MCPReadinessHook(AgentHook):
    """Retry application-owned MCP connections before the runner reads tools."""

    def __init__(self, provider: MCPProvider) -> None:
        super().__init__()
        self._provider = provider

    async def before_run(self, context: AgentRunHookContext) -> None:
        await self._provider.connect()
