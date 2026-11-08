"""Shell execution capability backed by shared preparation and session owners."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from cirno_core.agent.tools.base import Tool, ToolResult
from cirno_core.agent.tools.context import (
    ToolContext,
    current_request_session_key,
    tool_log_content_allowed,
)
from cirno_core.agent.tools.exec_session.formatting import format_session_poll
from cirno_core.agent.tools.exec_session.limits import clamp_session_int
from cirno_core.agent.tools.shell.preparation import CommandPreparation, PreparedCommand
from cirno_core.agent.tools.shell.schema import exec_parameters
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.processes.sessions.contracts import (
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_YIELD_MS,
    MAX_OUTPUT_CHARS,
    MAX_YIELD_MS,
)


class ExecTool(Tool):
    """Execute commands using the selected workspace and access policy."""

    _scopes = {"core", "subagent"}
    config_key = "exec"

    @classmethod
    def config_cls(cls):
        return ExecToolConfig

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.config.exec.enable

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        cfg = ctx.config.exec
        return cls(
            working_dir=ctx.workspace,
            max_runtime=cfg.max_runtime,
            max_runtime_limit=cfg.max_runtime_limit,
            idle_timeout=cfg.idle_timeout,
            idle_action=cfg.idle_action,
            restrict_to_workspace=ctx.config.restrict_to_workspace,
            webui_allow_local_service_access=ctx.config.webui_allow_local_service_access,
            sandbox=cfg.sandbox,
            path_prepend=cfg.path_prepend,
            path_append=cfg.path_append,
            sandbox_ro_binds=cfg.sandbox_ro_binds,
            sandbox_rw_binds=cfg.sandbox_rw_binds,
            allowed_env_keys=cfg.allowed_env_keys,
            allow_patterns=cfg.allow_patterns,
            deny_patterns=cfg.deny_patterns,
            session_manager=ctx.exec_session_manager,
        )

    def __init__(
        self,
        timeout: int | None = None,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        webui_allow_local_service_access: bool = True,
        sandbox: str = "",
        path_prepend: str = "",
        path_append: str = "",
        sandbox_ro_binds: list[str] | None = None,
        sandbox_rw_binds: list[str] | None = None,
        allowed_env_keys: list[str] | None = None,
        session_manager: ExecSessionManager | None = None,
        *,
        max_runtime: int | None = None,
        max_runtime_limit: int | None = None,
        idle_timeout: int = 300,
        idle_action: Literal["report", "terminate"] = "report",
    ):
        if timeout is not None and max_runtime is not None:
            raise ValueError("timeout and max_runtime are mutually exclusive")
        values: dict[str, Any] = {
            "idle_timeout": idle_timeout,
            "idle_action": idle_action,
            "path_prepend": path_prepend,
            "path_append": path_append,
            "sandbox": sandbox,
            "sandbox_ro_binds": sandbox_ro_binds or [],
            "sandbox_rw_binds": sandbox_rw_binds or [],
            "allowed_env_keys": allowed_env_keys or [],
            "allow_patterns": allow_patterns or [],
            "deny_patterns": deny_patterns or [],
        }
        if (runtime := max_runtime if max_runtime is not None else timeout) is not None:
            values["max_runtime"] = runtime
        if max_runtime_limit is not None:
            values["max_runtime_limit"] = max_runtime_limit
        self._exec_config = ExecToolConfig.model_validate(values)
        self.preparation = CommandPreparation(
            self._exec_config,
            working_dir=working_dir,
            restrict_to_workspace=restrict_to_workspace,
            allow_local_services=webui_allow_local_service_access,
        )
        self._session_manager = (
            session_manager if session_manager is not None else ExecSessionManager()
        )

    @property
    def name(self) -> str:
        return "exec"

    @property
    def parameters(self) -> dict[str, Any]:
        return exec_parameters(self._exec_config)

    @property
    def timeout(self) -> int:
        return self._exec_config.max_runtime

    @property
    def description(self) -> str:
        return "Execute a shell command. timeout and max_runtime are mutually exclusive."

    @property
    def exclusive(self) -> bool:
        return True

    async def execute(
        self,
        command: str | list[str] | None = None,
        cmd: str | None = None,
        working_dir: str | None = None,
        workdir: str | None = None,
        timeout: int | None = None,
        shell: str | None = None,
        login: bool | None = None,
        yield_time_ms: int | None = None,
        max_output_chars: int | None = None,
        max_output_tokens: int | None = None,
        max_runtime: int | None = None,
        **kwargs: Any,
    ) -> str:
        command = command or cmd
        working_dir = working_dir or workdir
        if not command:
            return ToolResult.error("Error: Missing command. Provide command or cmd.")
        if max_output_chars is None:
            max_output_chars = max_output_tokens

        if timeout is not None and max_runtime is not None:
            return ToolResult.error("Error: timeout and max_runtime are mutually exclusive.")
        try:
            prepared = self.preparation.prepare(
                command,
                working_dir,
                max_runtime if max_runtime is not None else timeout,
                shell,
                login,
            )
        except ValueError as exc:
            return ToolResult.error(f"Error: {exc}")
        if isinstance(prepared, str):
            return prepared
        return await self._execute_session(prepared, yield_time_ms, max_output_chars)

    async def execute_to_completion(self, command: str, working_dir: str) -> str:
        """Return the complete result for a trusted user shell command, without an agent observer."""
        try:
            prepared = self.preparation.prepare(command, working_dir)
        except ValueError as exc:
            return ToolResult.error(f"Error: {exc}")
        if isinstance(prepared, str):
            return prepared
        return await self._execute_session(prepared, None, None, until_exit=True)

    async def _execute_session(
        self,
        prepared: PreparedCommand,
        yield_time_ms: int | None,
        max_output_chars: int | None,
        *,
        until_exit: bool = False,
    ) -> str:
        try:
            session_id, poll = await self._session_manager.start(
                command=prepared.command,
                cwd=prepared.cwd,
                env=prepared.env,
                timeout=prepared.timeout,
                shell_program=prepared.shell_program,
                login=prepared.login,
                yield_time_ms=0
                if until_exit
                else clamp_session_int(
                    yield_time_ms,
                    DEFAULT_YIELD_MS,
                    0,
                    MAX_YIELD_MS,
                ),
                until_exit=until_exit,
                stdin=(
                    asyncio.subprocess.DEVNULL if yield_time_ms is None else asyncio.subprocess.PIPE
                ),
                idle_timeout=self._exec_config.idle_timeout,
                idle_action=self._exec_config.idle_action,
                owner_session_key=current_request_session_key(),
                log_content=tool_log_content_allowed(),
                max_output_chars=clamp_session_int(
                    max_output_chars,
                    DEFAULT_MAX_OUTPUT_CHARS,
                    1000,
                    MAX_OUTPUT_CHARS,
                ),
            )
            result = format_session_poll(session_id, poll)
            if not poll.done:
                result += "\nInitial wait ended; session remains active."
            return ToolResult.error(result) if poll.failed else result
        except Exception as exc:
            return ToolResult.error(f"Error executing command: {exc}")

    def approval_reason(self, params: dict[str, Any]) -> str | None:
        command = self.command_for_approval(params)
        if not command:
            return None
        try:
            prepared = self.preparation.prepare(
                command,
                params.get("working_dir") or params.get("workdir"),
                params.get("max_runtime", params.get("timeout")),
                params.get("shell"),
                params.get("login"),
            )
        except ValueError:
            return None  # Normal parameter validation reports the error; it grants no access.
        return str(prepared) if isinstance(prepared, str) else None

    def command_for_approval(self, params: dict[str, Any]) -> str | list[str] | None:
        return params.get("command") or params.get("cmd")
