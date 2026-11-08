"""Interact with or wait for one owned execution session."""

from __future__ import annotations

from typing import Any

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import ToolContext, current_request_session_key
from cirno_core.agent.tools.exec_session.formatting import format_session_poll
from cirno_core.agent.tools.exec_session.limits import clamp_session_int
from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.processes.sessions.contracts import (
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_UNTIL_EXIT_MS,
    DEFAULT_WAIT_FOR_MS,
    DEFAULT_YIELD_MS,
    MAX_WAIT_FOR_MS,
)
from cirno_core.processes.sessions.observer import observe_session


@tool_parameters(
    tool_parameters_schema(
        session_id=StringSchema("Session ID returned by exec."),
        input=StringSchema(
            "Text to send to stdin; omit to poll output.",
            nullable=True,
        ),
        close_stdin=BooleanSchema(
            description="Close stdin after sending input.",
            default=False,
        ),
        terminate=BooleanSchema(
            description="Terminate the session; use alone.",
            default=False,
        ),
        wait_for=StringSchema(
            "Return when this text appears in output.",
            min_length=1,
            nullable=True,
        ),
        until_exit=BooleanSchema(
            description="Wait for exit within timeout_ms; return the active session if the wait expires.",
            default=False,
        ),
        timeout_ms=IntegerSchema(
            description="Maximum wait: 1s normally, 10s for wait_for, 10m for until_exit.",
            minimum=0,
            maximum=MAX_WAIT_FOR_MS,
            nullable=True,
        ),
        required=["session_id"],
    )
)
class ExecSessionTool(Tool):
    """Interact with or wait for a running exec session."""

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
    def exclusive(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "exec_session"

    @property
    def description(self) -> str:
        return "Manage a session returned by exec."

    async def execute(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        session_id: str,
        input: str | None = None,
        close_stdin: bool = False,
        terminate: bool = False,
        wait_for: str | None = None,
        until_exit: bool = False,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            if wait_for == "":
                return ToolResult.error("Error: wait_for must not be empty.")
            if wait_for is not None and until_exit:
                return ToolResult.error("Error: wait_for and until_exit are mutually exclusive.")
            if terminate:
                if any(
                    (
                        input is not None,
                        close_stdin,
                        wait_for is not None,
                        until_exit,
                        timeout_ms is not None,
                    )
                ):
                    return ToolResult.error("Error: terminate must be used alone.")
                poll = await self._manager.write(
                    session_id=session_id,
                    chars=None,
                    close_stdin=False,
                    terminate=True,
                    yield_time_ms=0,
                    max_output_chars=DEFAULT_MAX_OUTPUT_CHARS,
                    owner_session_key=current_request_session_key(),
                )
                result = format_session_poll(session_id, poll)
                return ToolResult.error(result) if poll.failed else result

            default_timeout_ms = (
                DEFAULT_UNTIL_EXIT_MS
                if until_exit
                else DEFAULT_WAIT_FOR_MS
                if wait_for is not None
                else DEFAULT_YIELD_MS
            )
            wait_ms = clamp_session_int(timeout_ms, default_timeout_ms, 0, MAX_WAIT_FOR_MS)
            observation = await observe_session(
                self._manager,
                session_id=session_id,
                owner_session_key=current_request_session_key(),
                input=input,
                close_stdin=close_stdin,
                wait_for=wait_for,
                until_exit=until_exit,
                timeout_ms=wait_ms,
            )
            result = format_session_poll(session_id, observation.poll)
            if wait_for is not None and not observation.matched:
                result += f"\nWait target not observed: {wait_for!r}"
            if observation.expired and not observation.poll.done and not observation.matched:
                result += f"\nWait timed out after {wait_ms / 1000:g}s; session remains active."
            return ToolResult.error(result) if observation.poll.failed else result
        except KeyError:
            return ToolResult.error(f"Error: exec session not found: {session_id!r}")
        except Exception as exc:
            return ToolResult.error(f"Error managing exec session: {exc}")
