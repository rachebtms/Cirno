"""Resolve a command's workspace, runtime budget, environment and sandbox."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.sandbox import wrap_command
from cirno_core.agent.tools.shell.policy import WORKSPACE_BOUNDARY_NOTE, CommandPolicy
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.processes import platform
from cirno_core.processes.environment import ExecutionEnvironment
from cirno_core.processes.shells import resolve_shell
from cirno_core.security.workspace_access import current_tool_workspace
from cirno_core.security.workspace_policy import is_path_within


@dataclass(slots=True)
class PreparedCommand:
    command: str | list[str]
    cwd: str
    env: dict[str, str]
    timeout: int | None
    shell_program: str | None
    login: bool


class CommandPreparation:
    def __init__(
        self,
        config: ExecToolConfig,
        *,
        working_dir: str | None = None,
        restrict_to_workspace: bool = False,
        allow_local_services: bool = True,
    ):
        self.config = config
        self.working_dir = working_dir
        self.policy = CommandPolicy(
            config,
            restrict_to_workspace=restrict_to_workspace,
            allow_local_services=allow_local_services,
        )
        self.environment = ExecutionEnvironment(
            config.path_prepend, config.path_append, config.allowed_env_keys
        )

    def resolve_timeout(self, timeout: object) -> int | None:
        """Resolve a hard budget without changing the caller's requested duration."""
        if timeout is not None:
            if isinstance(timeout, bool) or not isinstance(timeout, int):
                raise ValueError("max_runtime must be an integer number of seconds")
            if self.config.max_runtime_limit == 0:
                if timeout < 0:
                    raise ValueError("max_runtime must be nonnegative; 0 means no time limit")
                return timeout or None
            if not 1 <= timeout <= self.config.max_runtime_limit:
                raise ValueError(
                    f"max_runtime must be between 1 and {self.config.max_runtime_limit} seconds"
                )
            return timeout
        return self.config.max_runtime or None

    def prepare(
        self,
        command: str | list[str],
        working_dir: str | None = None,
        timeout: int | None = None,
        shell: str | None = None,
        login: bool | None = None,
    ) -> PreparedCommand | str:
        access = current_tool_workspace(
            self.working_dir,
            restrict_to_workspace=self.policy.restrict_to_workspace,
            sandbox_restricts_workspace=bool(self.config.sandbox),
        )
        workspace_root = (
            str(access.project_path) if access.project_path is not None else self.working_dir
        )
        if working_dir:
            requested_dir = Path(working_dir).expanduser()
            cwd = str(
                requested_dir
                if requested_dir.is_absolute()
                else Path(workspace_root or os.getcwd()) / requested_dir
            )
        else:
            cwd = workspace_root or os.getcwd()
        # Prevent an LLM-supplied working_dir from escaping the configured
        # workspace when restrict_to_workspace is enabled (#2826). Without
        # this, a caller can pass working_dir="/etc" and then all absolute
        # paths under /etc would pass the _guard_command check that anchors
        # on cwd.
        if access.restrict_to_workspace and workspace_root:
            try:
                requested = Path(cwd).expanduser().resolve()
                resolved_root = Path(workspace_root).expanduser().resolve()
            except (OSError, RuntimeError, ValueError) as exc:
                raise ValueError(f"working_dir could not be resolved: {exc}") from exc
            if not is_path_within(requested, resolved_root):
                return ToolResult.error(
                    "Error: working_dir is outside the configured workspace"
                    + WORKSPACE_BOUNDARY_NOTE
                )

        # Full access is an explicit trust decision. Keep the application-level
        # command guard aligned with the selected access mode instead of
        # continuing to block commands after workspace restriction is disabled.
        if access.restrict_to_workspace:
            guard_error = self.policy.check(
                shlex.join(command) if isinstance(command, list) else command,
                cwd,
                restrict_to_workspace=True,
                workspace_root=workspace_root,
            )
            if guard_error:
                return guard_error

        if self.config.sandbox:
            if platform.IS_WINDOWS:
                raise ValueError(f"Sandbox {self.config.sandbox!r} is not supported on Windows")
            workspace = workspace_root or cwd
            wrapped = wrap_command(
                self.config.sandbox,
                shlex.join(command) if isinstance(command, list) else command,
                workspace,
                cwd,
                sandbox_ro_binds=[str(p) for p in self.policy.sandbox_ro_binds],
                sandbox_rw_binds=[str(p) for p in self.policy.sandbox_rw_binds],
            )
            command = shlex.split(wrapped) if isinstance(command, list) else wrapped
            cwd = str(Path(workspace).resolve())

        effective_timeout = self.resolve_timeout(timeout)
        env = self.environment.build()

        if isinstance(command, list):
            parent_path = os.environ.get("PATH", env.get("PATH", ""))
            env["PATH"] = self.environment.compose_path(parent_path)
        elif self.config.path_prepend or self.config.path_append:
            if platform.IS_WINDOWS:
                env["PATH"] = self.environment.compose_path(env.get("PATH", ""))
            else:
                command = self.environment.wrap_path_export(command, env)

        shell_program = resolve_shell(shell)

        return PreparedCommand(
            command=command,
            cwd=cwd,
            env=env,
            timeout=effective_timeout,
            shell_program=shell_program,
            login=False if login is None else login,
        )
