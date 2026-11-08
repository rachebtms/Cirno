"""Project task observations at the shared runner boundaries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from cirno_core.agent.hook import AgentHook, AgentHookContext
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.agent.tools.base import Tool
from cirno_core.providers.tool_calls import ToolCallRequest


class SubagentProgress(AgentHook):
    """Update task status at runner boundaries."""

    def __init__(
        self,
        status: SubagentStatus | None = None,
        *,
        check_active: Callable[[], None] | None = None,
        max_result_chars: int = 16000,
        on_status: Callable[[SubagentStatus], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self._status = status
        self._check_active = check_active
        self._max_result_chars = max_result_chars
        self._on_status = on_status

    def _remember_output(self, context: AgentHookContext) -> None:
        if self._status is None or context.error or context.response is None:
            return
        content = context.response.content
        if content and content.strip():
            self._status.result = content[: self._max_result_chars]
            self._status.partial = True

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        self._remember_output(context)
        if self._status is not None:
            self._status.tool_events = [
                {"name": call.name, "status": "running"} for call in context.tool_calls
            ]
        if self._status is not None and self._on_status is not None:
            await self._on_status(self._status)

    async def before_execute_tool(
        self,
        context: AgentHookContext,
        tool_call: ToolCallRequest,
        tool: Tool | None,
        params: dict[str, Any],
    ) -> None:
        if self._check_active is not None:
            self._check_active()

    async def after_iteration(self, context: AgentHookContext) -> None:
        if self._status is None:
            return
        self._status.iteration = context.iteration
        self._status.tool_events = list(context.tool_events)
        self._status.usage = context.usage
        self._remember_output(context)
        if context.error:
            self._status.error = str(context.error)
        if self._on_status is not None:
            await self._on_status(self._status)
