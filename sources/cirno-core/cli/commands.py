"""CLI commands for cirno."""

# pyright: reportConstantRedefinition=false, reportMissingTypeStubs=false, reportPrivateUsage=false, reportUnusedFunction=false, reportUnusedImport=false

import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Re-open stdout/stderr with UTF-8 encoding
        with suppress(Exception):
            for stream in (sys.stdout, sys.stderr):
                reconfigure = getattr(stream, "reconfigure", None)
                if callable(reconfigure):
                    reconfigure(encoding="utf-8", errors="replace")

# Keep console encoding setup before importing CLI UI/logging libraries.
import typer  # noqa: E402
from cirno.utils.log_config import configure_console_logging  # noqa: E402
from typer.core import TyperGroup  # noqa: E402

# Remove default handler and re-add with unified cirno format
_log_handler_id = configure_console_logging(sys.stderr)


from cirno import __logo__, __version__  # noqa: E402
from cirno.features import service as feature_support  # noqa: E402
from cirno.cli.agent import agent  # noqa: E402
from cirno.cli.gateway import create_gateway_app  # noqa: E402
from cirno.cli.gateway_runtime import _run_gateway  # noqa: E402
from cirno.cli.log_control import _set_cirno_logs  # noqa: E402
from cirno.cli.process_identity import set_cli_process_identity  # noqa: E402
from cirno.cli.provider import provider_app  # noqa: E402
from cirno.cli.runtime_config import (  # noqa: E402
    _load_inspection_config,
    _load_runtime_config,
    _model_display,
    _print_config_error,
    _print_model_setup_steps,
    _provider_setup_error,
)
from cirno.cli.webui import webui  # noqa: E402
from cirno.cli.webui_support import (  # noqa: E402
    _prepare_webui_bundle_for_gateway,
    _validate_gateway_startup,
)
from cirno.config.paths import get_workspace_path  # noqa: E402
from cirno.config.schema import Config  # noqa: E402
from cirno.utils.helpers import sanitize_surrogates as _sanitize_surrogates  # noqa: E402,F401
from cirno.utils.helpers import (  # noqa: E402
    sync_workspace_templates,
)
from rich.console import Console  # noqa: E402
from rich.markup import escape  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

app = typer.Typer(
    cls=TyperGroup,
    name="cirno",
    context_settings={"help_option_names": ["-h", "--help"]},
    help=f"{__logo__} cirno - Personal AI Assistant",
    epilog=(
        "Run `cirno` without a subcommand to open the web interface. "
        "Use `cirno agent --help` for agent options."
    ),
    invoke_without_command=True,
    no_args_is_help=False,
)

console = Console()

# Server-console pairing stays outside the agent/gateway lifecycle.


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} cirno v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    home: Path | None = typer.Option(
        None, "--home", help="Instance root directory",
        file_okay=False,
    ),
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """cirno - Personal AI Assistant."""
    if home is not None:
        from cirno.config.home import get_selected_home_path, set_home_path

        previous_home = get_selected_home_path()
        set_home_path(home)
        ctx.call_on_close(lambda: set_home_path(previous_home))
    # Editable/source installs can retain an older generated console script that
    # imports this Typer app directly instead of ``cirno.cli.entry``. Keep the
    # role identity correct until that launcher is regenerated.
    command = ctx.invoked_subcommand
    set_cli_process_identity([command] if command else ["webui"])
    if command is None:
        ctx.invoke(webui)


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    non_interactive_refresh: bool = typer.Option(False, "--refresh", help="Refresh config, preserving existing settings without prompting"),
):
    """Initialize cirno configuration and workspace."""
    from cirno.config.loader import get_config_path, load_config, save_config, set_config_path
    from cirno.config.schema import Config

    explicit_config = config is not None
    if config:
        config_path = Path(config).expanduser().resolve()
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")
    else:
        config_path = get_config_path()

    def _apply_workspace_override(loaded: Config) -> Config:
        if workspace:
            loaded.agents.defaults.workspace = workspace
        return loaded

    loaded_config = _apply_workspace_override(load_config(config_path) if config_path.exists() else Config())
    if not config_path.exists() or non_interactive_refresh or workspace:
        save_config(loaded_config, config_path)
    _onboard_plugins(config_path)

    # Create workspace, preferring the configured workspace path.
    workspace_path = get_workspace_path(loaded_config.workspace_path)
    if not workspace_path.exists():
        workspace_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created workspace at {workspace_path}")

    sync_workspace_templates(workspace_path)

    webui_cmd = "cirno webui"
    if explicit_config:
        webui_cmd += f' -c "{config_path}"'

    typer.echo(f"\n✓ cirno is ready. Run: {webui_cmd}")


def _onboard_plugins(config_path: Path) -> None:
    """Inject default config for all discovered channels (built-in + plugins)."""
    import json

    from cirno.channels.contracts import channel_default_config
    from cirno.channels.registry import discover_plugins
    from cirno.config.loader import merge_missing_defaults

    plugins = discover_plugins()
    if not plugins:
        return

    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    channels = data.setdefault("channels", {})
    for name, plugin in plugins.items():
        defaults = channel_default_config(plugin)
        if name not in channels:
            channels[name] = defaults
        else:
            channels[name] = merge_missing_defaults(channels[name], defaults)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _print_enable_options(
    extras: dict[str, list[str] | None],
    channel_plugins: dict[str, Any],
    config: Config,
) -> None:
    table = Table(title="Available Features")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Enabled")

    for item in sorted(set(channel_plugins) | set(extras)):
        plugin = channel_plugins.get(item)
        is_channel = plugin is not None
        enabled = (
            feature_support.channel_enabled(
                config,
                item,
                plugin,
                default_enabled=plugin.default_enabled,
            )
            if is_channel
            else feature_support.extra_installed(item, extras[item])
        )
        table.add_row(
            item,
            "channel" if is_channel else "feature",
            "[green]yes[/green]" if enabled else "[dim]no[/dim]",
        )

    console.print(table)


def _read_trigger_cli_message(message: str | None) -> str:
    """Read a trigger message from an argument or stdin."""
    if message and message.strip():
        return message
    try:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
            if content.strip():
                return content
    except OSError as exc:
        console.print(f"[red]Error reading trigger message: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print("[red]Error: trigger message is required[/red]")
    raise typer.Exit(1)


@app.command()
def trigger(
    trigger_id: str = typer.Argument(..., help="Trigger ID returned by /trigger"),
    message: str | None = typer.Argument(None, help="Message to deliver; stdin is used when omitted"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Deliver a local trigger message to its bound chat session."""
    from cirno.triggers.local_store import (
        LocalTriggerStore,
        TriggerDisabledError,
        TriggerNotFoundError,
        TriggerStoreError,
    )

    runtime_config = _load_runtime_config(config, workspace)
    content = _read_trigger_cli_message(message)
    store = LocalTriggerStore(runtime_config.workspace_path)
    try:
        delivery = store.enqueue(trigger_id, content)
    except (TriggerNotFoundError, TriggerDisabledError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    except (TriggerStoreError, ValueError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Queued[/green] {delivery.trigger_id} ({delivery.id})")


# ============================================================================
# ============================================================================




# ============================================================================
# WebUI Launcher
# ============================================================================

app.command(name="webui")(webui)


# ============================================================================
# Gateway / Server
# ============================================================================


app.add_typer(
    create_gateway_app(
        console=console,
        log_handler_id=_log_handler_id,
        load_runtime_config=_load_runtime_config,
        run_gateway=_run_gateway,
        validate_startup_config=_validate_gateway_startup,
        prepare_webui_bundle=lambda config, mode: _prepare_webui_bundle_for_gateway(
            config,
            mode=mode,
        ),
    ),
    name="gateway",
)


# ============================================================================
# Agent Commands
# ============================================================================


app.command(name="agent")(agent)


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status(
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show channel status."""
    from cirno.channels.registry import discover_all

    _, loaded = _load_inspection_config(config=config)

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled")

    for name, cls in sorted(discover_all().items()):
        section = getattr(loaded.channels, name, None)
        if section is None:
            enabled = False
        elif isinstance(section, dict):
            enabled = cast(dict[str, Any], section).get("enabled", False)
        else:
            enabled = getattr(section, "enabled", False)
        table.add_row(
            cls.display_name,
            "[green]\u2713[/green]" if enabled else "[dim]\u2717[/dim]",
        )

    console.print(table)


@channels_app.command("login")
def channels_login(
    channel_name: str = typer.Argument(..., help="Channel name (e.g. telegram)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-authentication even if already logged in"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Authenticate with a channel via QR code or other interactive login."""
    from cirno.bus.queue import MessageBus
    from cirno.channels.registry import discover_all

    _, loaded = _load_inspection_config(config=config)
    channel_cfg: Any = getattr(loaded.channels, channel_name, None) or {}

    # Validate channel exists
    all_channels = discover_all()
    if channel_name not in all_channels:
        available = ", ".join(all_channels.keys())
        console.print(f"[red]Unknown channel: {channel_name}[/red]  Available: {available}")
        raise typer.Exit(1)

    console.print(f"{__logo__} {all_channels[channel_name].display_name} Login\n")

    channel_factory = all_channels[channel_name]
    channel = channel_factory(channel_cfg, bus=MessageBus())

    success = asyncio.run(channel.login(force=force))

    if not success:
        raise typer.Exit(1)


# ============================================================================
# Plugin Commands
# ============================================================================

plugins_app = typer.Typer(help="Manage optional cirno features")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list(
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """List optional cirno features."""
    from cirno.channels.registry import discover_plugins
    from cirno.config.loader import load_config, set_config_path

    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
    if resolved_config_path is not None:
        set_config_path(resolved_config_path)

    _print_enable_options(
        feature_support.optional_dependency_groups(),
        discover_plugins(),
        load_config(resolved_config_path),
    )


@plugins_app.command("enable")
def plugins_enable(
    name: str = typer.Argument(..., help="Feature name (e.g. weixin, matrix, bedrock)"),
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show optional package install logs"),
):
    """Enable a cirno feature."""
    from cirno.config.loader import get_config_path, set_config_path

    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
    if resolved_config_path is not None:
        set_config_path(resolved_config_path)
    resolved_config_path = resolved_config_path or get_config_path()
    _set_cirno_logs(logs)

    try:
        payload = feature_support.enable_optional_feature(
            name,
            config_path=resolved_config_path,
            runner=feature_support.run_install_command,
        )
    except feature_support.OptionalFeatureError as exc:
        console.print(f"[red]{escape(exc.message)}[/red]")
        raise typer.Exit(1) from exc

    message = payload.get("last_action", {}).get("message") or f"Enabled feature '{name}'"
    console.print(f"[green]{escape(message)}[/green]")


@plugins_app.command("disable")
def plugins_disable(
    name: str = typer.Argument(..., help="Channel name (e.g. telegram, websocket)"),
    config_path: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Disable a cirno channel feature."""
    from cirno.config.loader import get_config_path, set_config_path

    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else None
    if resolved_config_path is not None:
        set_config_path(resolved_config_path)
    resolved_config_path = resolved_config_path or get_config_path()

    try:
        payload = feature_support.disable_optional_feature(name, config_path=resolved_config_path)
    except feature_support.OptionalFeatureError as exc:
        console.print(f"[red]{escape(exc.message)}[/red]")
        raise typer.Exit(1) from exc

    message = payload.get("last_action", {}).get("message") or f"Disabled channel '{name}'"
    console.print(f"[green]{escape(message)}[/green] in {resolved_config_path}")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status(
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Show cirno status."""
    config_path, loaded = _load_inspection_config(config=config, workspace=workspace)
    workspace_path = loaded.workspace_path

    console.print(f"{__logo__} cirno Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(
        f"Workspace: {workspace_path} "
        f"{'[green]✓[/green]' if workspace_path.exists() else '[red]✗[/red]'}"
    )

    if config_path.exists():
        from cirno.config.errors import ConfigLoadError
        from cirno.config.loader import resolve_config_env_vars, resolve_env_refs
        from cirno.providers.registry import PROVIDERS

        _model, _preset_tag = _model_display(loaded)
        console.print(f"Model: {_model}{_preset_tag}")

        provider_ready = False
        try:
            resolved = resolve_config_env_vars(
                loaded.model_copy(deep=True),
                config_path=config_path,
            )
        except ConfigLoadError as exc:
            console.print("Agent: [red]✗ configuration is not ready[/red]")
            _print_config_error(exc)
        else:
            provider_error = _provider_setup_error(resolved)
            if provider_error:
                console.print(Text(f"Agent: ✗ {provider_error}", style="red"))
                console.print("Complete provider/model setup:")
                _print_model_setup_steps(config_path)
            else:
                provider_ready = True
                console.print("Agent: [green]✓ provider/model configuration is ready[/green]")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(loaded.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if resolve_env_refs(p.api_base or ""):
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(resolve_env_refs(p.api_key or ""))
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")

        if provider_ready:
            console.print()
            console.print('Next: [cyan]cirno agent -m "Hello!"[/cyan]')
            console.print(
                "[dim]Status does not call the model or verify network access and credentials.[/dim]"
            )
    else:
        console.print("Agent: [red]✗ configuration file not found[/red]")
        console.print("Create the provider/model configuration:")
        _print_model_setup_steps(config_path)


# ============================================================================
# OAuth Login
# ============================================================================

app.add_typer(provider_app, name="provider")


if __name__ == "__main__":
    app()
