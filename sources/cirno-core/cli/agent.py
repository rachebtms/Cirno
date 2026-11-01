"""Single-request agent command."""

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from typing import Any

import typer
from cirno.cli.log_control import _set_cirno_logs
from cirno.cli.runtime_config import (
    _load_runtime_config,
    _print_agent_start_error,
)
from cirno.config.schema import Config
from rich.console import Console

console = Console()

_CLASSIC_DEPENDENCIES = {
    "AgentLoop": ("cirno.agent.loop", "AgentLoop"),
    "StreamRenderer": ("cirno.cli.stream", "StreamRenderer"),
    "consume_restart_notice_from_env": (
        "cirno.utils.restart",
        "consume_restart_notice_from_env",
    ),
    "is_default_workspace": ("cirno.config.paths", "is_default_workspace"),
    "sync_workspace_templates": ("cirno.utils.helpers", "sync_workspace_templates"),
}


def __getattr__(name: str) -> Any:
    """Load command dependencies when first used."""
    dependency = _CLASSIC_DEPENDENCIES.get(name)
    if dependency is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = dependency
    value = getattr(importlib.import_module(module_name), attribute)
    globals()[name] = value
    return value


def _classic_dependency(name: str) -> Any:
    if name in globals():
        return globals()[name]
    return __getattr__(name)


def agent(
    message: str | None = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    markdown: bool = typer.Option(
        True,
        "--markdown/--no-markdown",
        help="Render assistant output as Markdown",
    ),
    logs: bool = typer.Option(
        False,
        "--logs/--no-logs",
        help="Show cirno runtime logs during chat",
    ),
):
    """Send one message and print the response."""
    if message is None:
        raise typer.BadParameter("Use --message for a single request, or run cirno webui for chat.")
    runtime_config = _load_runtime_config(config, workspace)
    _run_classic(runtime_config, message=message, session_id=session_id, markdown=markdown, logs=logs)


def _run_classic(runtime_config: Config, *, message: str | None, session_id: str | None,
                 markdown: bool, logs: bool) -> None:
    """Run a single request and close its resources."""
    from cirno.agent.hooks import create_file_edit_activity_hook
    from cirno.agent.tools.mcp import MCPProvider
    from cirno.agent.tools.registry import ToolRegistry
    from cirno.bus.queue import MessageBus
    from cirno.cli import terminal as cli_terminal
    from cirno.cli.stream import ThinkingSpinner
    from cirno.cron.service import CronService
    from cirno.providers.factory import make_provider
    from cirno.utils.restart import (
        format_restart_completed_message,
        should_show_cli_restart_notice,
    )
    from cirno.utils.tool_hints import format_tool_event_hints

    agent_loop_class = _classic_dependency("AgentLoop")
    stream_renderer_class = _classic_dependency("StreamRenderer")
    consume_restart_notice_from_env = _classic_dependency("consume_restart_notice_from_env")
    sync_workspace_templates = _classic_dependency("sync_workspace_templates")

    session_id = session_id or "cli:direct"

    try:
        provider = make_provider(runtime_config)
    except ValueError as exc:
        _print_agent_start_error(exc)
        raise typer.Exit(1) from exc

    sync_workspace_templates(runtime_config.workspace_path)

    bus = MessageBus()

    # Create cron service with workspace-scoped store
    cron_store_path = runtime_config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    tools = ToolRegistry()
    mcp_provider = MCPProvider.from_config(runtime_config, tools)

    _set_cirno_logs(logs)

    try:
        agent_loop = agent_loop_class.from_config(
            runtime_config,
            bus,
            provider=provider,
            cron_service=cron,
            hook_factories=[create_file_edit_activity_hook],
            tool_registry=tools,
        )
    except ValueError as exc:
        _print_agent_start_error(exc)
        raise typer.Exit(1) from exc
    restart_notice = consume_restart_notice_from_env()
    if restart_notice and should_show_cli_restart_notice(restart_notice, session_id):
        cli_terminal._print_agent_response(
            format_restart_completed_message(restart_notice.started_at_raw),
            render_markdown=False,
        )

    async def _close_runtime() -> None:
        try:
            await agent_loop.aclose()
        finally:
            await mcp_provider.aclose()

    # Shared reference for progress callbacks
    _thinking: ThinkingSpinner | None = None

    def _make_progress(
        renderer: Any | None = None,
    ) -> Callable[..., Awaitable[None]]:
        reasoning_buffer = cli_terminal._ReasoningBuffer()

        async def _cli_progress(
            content: str,
            *,
            tool_hint: bool = False,
            tool_events: list[dict[str, Any]] | None = None,
            reasoning: bool = False,
            **_kwargs: Any,
        ) -> None:
            ch = agent_loop.channels_config

            if _kwargs.get("reasoning_end"):
                if ch and not ch.show_reasoning:
                    reasoning_buffer.clear()
                else:
                    cli_terminal._flush_cli_reasoning(reasoning_buffer, _thinking, renderer)
                return

            if reasoning:
                if ch and not ch.show_reasoning:
                    reasoning_buffer.clear()
                    return
                text = reasoning_buffer.add(content)
                if text:
                    cli_terminal._print_cli_reasoning(text, _thinking, renderer)
                return
            if ch and tool_hint and not ch.send_tool_hints:
                return
            if ch and not tool_hint and not ch.send_progress:
                return
            if tool_hint and tool_events:
                content = format_tool_event_hints(
                    tool_events, max_length=runtime_config.agents.defaults.tool_hint_max_length,
                )
            cli_terminal._print_cli_progress_line(content, _thinking, renderer)

        return _cli_progress

    # Single message mode — direct call, no bus needed
    async def run_once() -> None:
        try:
            await mcp_provider.connect()
            renderer = stream_renderer_class(
                render_markdown=markdown,
                bot_name=runtime_config.agents.defaults.bot_name,
                bot_icon=runtime_config.agents.defaults.bot_icon,
            )
            response = await agent_loop.process_direct(
                message,
                session_id,
                on_progress=_make_progress(renderer),
                on_stream=renderer.on_delta,
                on_stream_end=renderer.on_end,
            )
            if not renderer.streamed:
                await renderer.close()
                print_kwargs: dict[str, Any] = {}
                if renderer.header_printed:
                    print_kwargs["show_header"] = False
                cli_terminal._print_agent_response(
                    response.content if response else "",
                    render_markdown=markdown,
                    metadata=response.metadata if response else None,
                    **print_kwargs,
                )
        finally:
            await _close_runtime()

    asyncio.run(run_once())
