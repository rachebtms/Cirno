"""List execution sessions visible to the current conversation."""

from __future__ import annotations

from typing import Any

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import ToolContext, current_request_session_key
from cirno_core.agent.tools.schema import tool_parameters_schema
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.processes.sessions import ExecSessionManager


@tool_parameters(tool_parameters_schema())
class ListExecSessionsTool(Tool):
    """List active exec sessions."""

    _scopes = {"core", "subagent"}
    config_key = "exec"

    @classmethod
    def config_cls(cls):
        return ExecToolConfig

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.config.exec.enable

    def __init__(
        self,
        *,
        manager: ExecSessionManager | None = None,
    ) -> None:
        self._manager = manager if manager is not None else ExecSessionManager()

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls(manager=ctx.exec_session_manager)

    @property
    def name(self) -> str:
        return "list_exec_sessions"

    @property
    def description(self) -> str:
        return "List active exec sessions."

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:
        try:
            sessions = await self._manager.list(
                owner_session_key=current_request_session_key(),
            )
            if not sessions:
                return "No active exec sessions."
            lines: list[str] = []
            for info in sessions:
                command = " ".join(info.command.split())
                if len(command) > 120:
                    command = command[:119] + "..."
                status = (
                    "finished"
                    if info.finish_reason is not None
                    else ("stopping" if info.stopping else "running")
                )
                remaining = "unlimited" if info.remaining_s is None else f"{info.remaining_s:.1f}s"
                silent = bool(info.idle_timeout and info.idle_s >= info.idle_timeout)
                lines.append(
                    f"{info.session_id} | {status} | elapsed={info.elapsed_s:.1f}s "
                    f"| output_idle={info.idle_s:.1f}s | silent={str(silent).lower()} "
                    f"| remaining={remaining} | reason={info.finish_reason or '-'} "
                    f"| cwd={info.cwd} | {command}"
                )
                if info.cleanup_error is not None:
                    lines.append(f"Cleanup failed: {info.cleanup_error}")
            return "\n".join(lines)
        except Exception as exc:
            return ToolResult.error(f"Error listing exec sessions: {exc}")
