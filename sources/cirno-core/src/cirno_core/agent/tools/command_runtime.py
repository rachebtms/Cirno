"""Shared hard runtime policy for local and remote command tools."""

from cirno_core.agent.tools.schema import IntegerSchema
from cirno_core.agent.tools.shell_config import ExecToolConfig


def resolve_command_runtime(config: ExecToolConfig, requested: object = None) -> int | None:
    if requested is None:
        return config.max_runtime or None
    if isinstance(requested, bool) or not isinstance(requested, int):
        raise ValueError("max_runtime must be an integer number of seconds")
    if config.max_runtime_limit == 0:
        if requested < 0:
            raise ValueError("max_runtime must be nonnegative; 0 means no time limit")
        return requested or None
    if not 1 <= requested <= config.max_runtime_limit:
        raise ValueError(f"max_runtime must be between 1 and {config.max_runtime_limit} seconds")
    return requested


def command_runtime_parameters(config: ExecToolConfig) -> dict[str, IntegerSchema]:
    limit_note = (
        f"Explicit requests must not exceed {config.max_runtime_limit}s. "
        if config.max_runtime_limit else "Explicit requests have no upper limit; 0 means unlimited. "
    )
    bounds = {"minimum": 1 if config.max_runtime_limit else 0, "maximum": config.max_runtime_limit or None}
    return {
        "max_runtime": IntegerSchema(
            description=(
                "Hard runtime budget in seconds for command execution. Omit for the shared Shell execution default "
                f"({'unlimited' if config.max_runtime == 0 else str(config.max_runtime) + 's'}). "
                f"{limit_note}Output does not extend the budget."
            ), **bounds,
        ),
        "timeout": IntegerSchema(
            description="Compatibility alias for max_runtime; cannot be combined with it.", **bounds,
        ),
    }
