"""Configuration loading and diagnostics shared by CLI commands."""


import typer
from cirno_core.config.schema import Config
from rich.console import Console
from rich.text import Text

__all__ = ['_provider_setup_error', '_validate_session_storage']

console = Console()


















def _validate_session_storage(config: Config, *, workspace_override: str | None = None) -> None:
    """Reject overlapping session storage before startup creates workspace files."""
    from cirno_core.config.loader import get_config_path

    config_path = get_config_path().expanduser().resolve(strict=False)
    data_dir = config.runtime_data_dir or config_path.parent / "state"
    sessions = (data_dir / "sessions").resolve(strict=False)
    workspace = config.workspace_path.resolve(strict=False)
    if not sessions.is_relative_to(workspace):
        return

    source = "--workspace" if workspace_override else "agents.defaults.workspace"
    console.print(Text("Cannot start: chat history must be outside the workspace.", style="red"))
    console.print()
    console.print(Text(f"Workspace ({source}): {workspace}"))
    console.print(Text(f"Chat history: {sessions}"))
    console.print()
    console.print("To fix, keep the workspace in place:")
    console.print("  1. Stop the instance and back up its files.")
    console.print("  2. Move config.json and its runtime data outside the workspace.")
    console.print("  3. Restart with --config pointing to the moved config file.")
    console.print("Configuration help: documents/configuration.md")
    raise typer.Exit(1)




def _provider_setup_error(config: Config) -> str | None:
    """Return a local provider/model configuration error, or None."""
    from cirno_core.providers.factory import validate_provider_setup

    try:
        validate_provider_setup(config)
    except ValueError as exc:
        return str(exc)
    return None
