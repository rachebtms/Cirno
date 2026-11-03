"""Start the complete Cirno service; configuration and administration live in Web UI."""

from pathlib import Path

import typer
from rich.console import Console

from cirno_core import __version__
from cirno_core.config.errors import ConfigLoadError
from cirno_core.config.home import get_selected_instance_path, set_instance_path
from cirno_core.config.loader import get_config_path, load_config, save_config, set_config_path, resolve_config_env_vars
from cirno_core.utils.log_config import configure_console_logging
from cirno_server.channels.websocket.runtime import WebSocketConfig
from cirno_server.application import run_server
from cirno_server.cli.runtime_config import _provider_setup_error, _validate_session_storage
from cirno_server.lifecycle.runtime import ServerAlreadyRunningError

app = typer.Typer(add_completion=False, context_settings={"help_option_names": ["-h", "--help"]})
console = Console()


def _version(value: bool) -> None:
    if value:
        typer.echo(f"Cirno {__version__}")
        raise typer.Exit()


@app.command()
def start(
    ctx: typer.Context,
    home: Path | None = typer.Option(None, "--home", help="Instance directory", file_okay=False),
    config: Path | None = typer.Option(None, "--config", "-c", help="Configuration file"),
    host: str | None = typer.Option(None, "--host", help="Web UI bind address"),
    port: int | None = typer.Option(None, "--port", "-p", min=1, max=65535, help="Web UI port"),
    health_port: int | None = typer.Option(None, "--health-port", min=1, max=65535, help="Service health port"),
    workspace: Path | None = typer.Option(None, "--workspace", help="Working directory override"),
    verbose: bool = typer.Option(False, "--verbose", help="Show debug logs"),
    version: bool = typer.Option(False, "--version", "-v", callback=_version, is_eager=True),
) -> None:
    """Run Cirno and its Web UI. Complete initial setup in your browser."""
    import sys
    configure_console_logging(sys.stderr)
    if home is not None:
        previous = get_selected_instance_path()
        set_instance_path(home)
        ctx.call_on_close(lambda: set_instance_path(previous))
    if config is not None:
        set_config_path(config.expanduser().resolve())
    path = get_config_path()
    try:
        from cirno_server.backup.archive import Backups
        if Backups(path).apply_pending():
            console.print("Cirno backup restored. Sign in with the restored account.")
        fresh = not path.exists()
        settings = load_config(path)
        websocket = WebSocketConfig.model_validate(getattr(settings.channels, "websocket", {}) or {})
        websocket.enabled = True
        if fresh:
            websocket.browser_setup = True
        if host is not None:
            websocket.host = host
        if port is not None:
            websocket.port = port
        settings.channels.websocket = websocket.model_dump(by_alias=True)
        if health_port is not None:
            settings.server.health_port = health_port
        if workspace is not None:
            settings.agents.defaults.workspace = str(workspace.expanduser().resolve())
        resolved = resolve_config_env_vars(settings)
        _validate_session_storage(resolved, workspace_override=str(workspace) if workspace else None)
        if fresh:
            save_config(settings, path)
        run_server(resolved, port=health_port, verbose=verbose,
                     webui_bundle_mode="auto", unconfigured_provider_error=_provider_setup_error(resolved))
    except (ConfigLoadError, ServerAlreadyRunningError, ValueError, OSError) as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(1) from exc
