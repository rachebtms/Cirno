"""Model-facing command execution parameters."""

from typing import Any

from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.agent.tools.command_runtime import command_runtime_parameters
from cirno_core.processes import platform
from cirno_core.processes.sessions.contracts import MAX_OUTPUT_CHARS, MAX_YIELD_MS


def exec_parameters(config: ExecToolConfig) -> dict[str, Any]:
    return tool_parameters_schema(
        command=StringSchema("The shell command to execute"),
        cmd=StringSchema("Compatibility alias for command"),
        working_dir=StringSchema("Optional working directory for the command"),
        workdir=StringSchema("Compatibility alias for working_dir"),
        **command_runtime_parameters(config),
        shell=StringSchema(
            (
                "Shell override; omit for PowerShell, or pass 'cmd' for cmd.exe."
                if platform.IS_WINDOWS
                else "Shell override; omit for bash, or pass 'sh' or 'zsh'."
            ),
            nullable=True,
        ),
        login=BooleanSchema(
            description="Run bash/zsh as a login shell.",
            default=False,
            nullable=True,
        ),
        stdin=StringSchema(
            "Child input: closed disables input; pipe allows later shell.session writes. "
            "Omit for legacy behavior (pipe when yield_time_ms is supplied).",
            enum=["closed", "pipe"],
        ),
        yield_time_ms=IntegerSchema(
            description="Return after this many milliseconds if still running (default 1000, max 30000); execution continues.",
            minimum=0,
            maximum=MAX_YIELD_MS,
            nullable=True,
        ),
        max_output_chars=IntegerSchema(
            description="Session output limit in characters (default 10000, max 50000).",
            minimum=1000,
            maximum=MAX_OUTPUT_CHARS,
            nullable=True,
        ),
        max_output_tokens=IntegerSchema(
            description="Compatibility alias for max_output_chars.",
            minimum=1000,
            maximum=MAX_OUTPUT_CHARS,
            nullable=True,
        ),
    )
