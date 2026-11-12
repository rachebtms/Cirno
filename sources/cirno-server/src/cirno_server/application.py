"""Foreground service runtime and lifecycle helpers."""

import asyncio
from collections.abc import Awaitable, Coroutine
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any, cast

import typer
from cirno_core import __logo__, __version__
from cirno_core.agent.hooks import create_file_edit_activity_hook
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.mcp.provider import MCPProvider
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.queue import MessageBus
from cirno_core.config.paths import get_data_dir
from cirno_core.config.schema import Config
from cirno_core.security.network import is_loopback_host
from cirno_core.session.manager import SessionManager
from cirno_core.session.router_session import ensure_router_session
from cirno_core.utils.home_templates import sync_home_templates
from cirno_core.utils.token_encoding import warmup_token_encoding
from rich.console import Console

from cirno_server.channels.delivery.publish import publish_to_channel
from cirno_server.cli.dock import watch_gateway_icon
from cirno_server.cli.startup_browser import open_when_ready
from cirno_server.cli.webui_support import (
    _gateway_health_bind_note,
    _gateway_health_url,
    _host_for_local_browser,
    _prepare_webui_bundle_for_gateway,
    _print_foreground_port_conflict,
    _tcp_endpoint_reachable,
    _webui_browser_url,
    _webui_channel_enabled,
    _webui_endpoint_reachable,
)
from cirno_server.lifecycle.contracts import ServerHealthIdentity
from cirno_server.lifecycle.development import watch_dev_server
from cirno_server.lifecycle.health_server import HealthListener
from cirno_server.lifecycle.instance import ServerInstance
from cirno_server.lifecycle.mcp import MCPReadinessHook
from cirno_server.lifecycle.runtime import ServerRuntime
from cirno_server.lifecycle.shutdown import close_runtime, install_shutdown_handlers
from cirno_server.scheduling.agent_jobs import ScheduledAgentJobs
from cirno_server.webui.build import BuildMode
from cirno_server.webui.dev import WebUIDevError, WebUIDevServer

__all__ = ["run_server"]

console = Console()


def _print_gateway_health_endpoint(host: str, port: int) -> None:
    """Print a usable health URL and make non-loopback binds explicit."""
    console.print(
        f"[green]✓[/green] Health endpoint: {_gateway_health_url(host, port)}"
        f"{_gateway_health_bind_note(host)}"
    )
    if is_loopback_host(host):
        return

    console.print(
        "[yellow]Warning: the unauthenticated health endpoint is listening beyond loopback "
        "and may be reachable from other devices. "
        f"Keep port {port} private or protect it with a firewall or reverse proxy.[/yellow]"
    )


def run_server(
    config: Config,
    *,
    port: int | None = None,
    verbose: bool = False,
    open_browser_url: str | None = None,
    open_browser_ready_url: str | None = None,
    webui_static_dist: bool = True,
    webui_bundle_mode: BuildMode = "warn",
    health_server_enabled: bool = True,
    unconfigured_provider_error: str | None = None,
    webui_dev_server: WebUIDevServer | None = None,
    gateway_instance: ServerInstance | None = None,
) -> None:
    """Claim this gateway instance before initializing runtime writers."""
    from cirno_core.config.loader import get_config_path

    from cirno_server.lifecycle.health import create_health_identity

    port = port if port is not None else config.server.health_port
    instance = gateway_instance or ServerInstance.resolve(config_path=get_config_path())
    gateway_runtime = ServerRuntime(paths=instance.paths)
    with gateway_runtime.foreground_instance(instance.start_options(port=port, verbose=verbose)):
        from cirno_server.maintenance.migrations.registry import migrate_instance
        migrate_instance(instance.config_path)
        config.last_run_version = __version__
        _run_claimed_server(
            config,
            port=port,
            gateway_instance=instance,
            gateway_runtime=gateway_runtime,
            health_identity=create_health_identity(instance),
            open_browser_url=open_browser_url,
            open_browser_ready_url=open_browser_ready_url,
            webui_static_dist=webui_static_dist,
            webui_bundle_mode=webui_bundle_mode,
            health_server_enabled=health_server_enabled,
            unconfigured_provider_error=unconfigured_provider_error,
            webui_dev_server=webui_dev_server,
        )


def _run_claimed_server(
    config: Config,
    *,
    port: int,
    gateway_instance: ServerInstance,
    gateway_runtime: ServerRuntime,
    health_identity: ServerHealthIdentity,
    open_browser_url: str | None,
    open_browser_ready_url: str | None,
    webui_static_dist: bool,
    webui_bundle_mode: BuildMode,
    health_server_enabled: bool,
    unconfigured_provider_error: str | None,
    webui_dev_server: WebUIDevServer | None,
) -> None:
    """Initialize and run only while the caller holds the gateway lifecycle claim."""
    from cirno_core.agent.model_presets import load_model_preset_catalog
    from cirno_core.agent.tools.message import MessageTool
    from cirno_core.agent.turn_delivery import TurnDeliveryFactory
    from cirno_core.config.watcher import watch_config_file
    from cirno_core.cron.service import CronService
    from cirno_core.providers.factory import (
        ProviderSnapshot,
        build_provider_snapshot,
        build_unconfigured_provider_snapshot,
        load_provider_snapshot,
    )
    from cirno_core.providers.fallback_provider import FallbackProvider
    from cirno_core.session.recovery.coordinator import RecoveryCoordinator
    from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
    from cirno_core.session.webui_turns.models import build_webui_fallback_model_observer
    from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy
    from cirno_core.triggers.local_runner import run_local_trigger_queue
    from cirno_core.triggers.local_store import LocalTriggerStore
    from cirno_usage import record_llm_call

    from cirno_server.channels.manager import ChannelManager

    webui_url = _webui_browser_url(config)
    gateway_host_for_browser = _host_for_local_browser(config.server.health_host)
    if health_server_enabled and _tcp_endpoint_reachable(gateway_host_for_browser, port):
        _print_foreground_port_conflict(
            webui_url=webui_url,
            gateway_host=config.server.health_host,
            gateway_port=port,
        )
        raise typer.Exit(1)
    if _webui_channel_enabled(config) and _webui_endpoint_reachable(webui_url):
        _print_foreground_port_conflict(
            webui_url=webui_url,
            gateway_host=config.server.health_host,
            gateway_port=port,
        )
        raise typer.Exit(1)

    console.print(f"{__logo__} Starting Cirno version {__version__} on port {port}...")
    warmup_token_encoding()
    _prepare_webui_bundle_for_gateway(
        config,
        mode=webui_bundle_mode,
        webui_static_dist=webui_static_dist,
    )
    sync_home_templates()
    bus = MessageBus()
    fallback_model_observer = build_webui_fallback_model_observer(bus)

    def _observe_provider(snapshot: ProviderSnapshot) -> ProviderSnapshot:
        snapshot.provider.set_llm_call_observer(partial(record_llm_call, path=get_data_dir() / "llm_usage.sqlite3"))
        if isinstance(snapshot.provider, FallbackProvider):
            snapshot.provider.set_fallback_model_observer(fallback_model_observer)
        return snapshot

    def _load_gateway_provider_snapshot(
        *args: Any,
        **kwargs: Any,
    ) -> ProviderSnapshot:
        try:
            return _observe_provider(load_provider_snapshot(*args, **kwargs))
        except ValueError as exc:
            if unconfigured_provider_error is None:
                raise
            return _observe_provider(build_unconfigured_provider_snapshot(config, str(exc)))

    if unconfigured_provider_error is not None:
        provider_snapshot = _observe_provider(
            build_unconfigured_provider_snapshot(config, unconfigured_provider_error)
        )
    else:
        try:
            provider_snapshot = _observe_provider(build_provider_snapshot(config))
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from exc
    session_manager = SessionManager(config.workspace_path)

    config_path = str(gateway_instance.config_path)

    # Automations belong to the instance, independent of task directories.
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    from cirno_core.notifications.service_errors import report_service_error
    cron = CronService(cron_store_path, admission=bus.admission,
                       on_error=partial(report_service_error, get_data_dir(), "Scheduler"))
    trigger_store = LocalTriggerStore(get_data_dir() / "triggers")

    webui_route_policy = WebuiTurnRoutePolicy(session_manager)
    turn_delivery_factory = TurnDeliveryFactory(
        bus,
        route_policy=webui_route_policy,
        route_admission=webui_route_policy.admit,
    )

    tools = ToolRegistry()
    mcp_provider = MCPProvider.from_config(config, tools)

    recovery = RecoveryCoordinator(
        sessions=session_manager,
        bus=bus,
        resume_settings=config.agents.defaults.resume,
    )

    # Create agent with cron service
    agent = AgentLoop.from_config(
        config,
        bus,
        provider=provider_snapshot.provider,
        model=provider_snapshot.model,
        context_window_tokens=provider_snapshot.context_window_tokens,
        cron_service=cron,
        session_manager=session_manager,
        provider_snapshot_loader=_load_gateway_provider_snapshot,
        preset_catalog_loader=load_model_preset_catalog,
        turn_delivery_factory=turn_delivery_factory,
        provider_signature=provider_snapshot.signature,
        local_trigger_store=trigger_store,
        hooks=[MCPReadinessHook(mcp_provider)],
        hook_factories=[create_file_edit_activity_hook],
        tool_registry=tools,
        recovery_admission=recovery,
    )

    def _schedule_webui_background(awaitable: Awaitable[None]) -> None:
        agent.schedule_background(cast(Coroutine[Any, Any, None], awaitable))

    webui_turn_coordinator = WebuiTurnCoordinator(
        bus=bus,
        sessions=session_manager,
        schedule_background=_schedule_webui_background,
        recovery=recovery,
    )
    deliver_to_channel = partial(
        publish_to_channel,
        bus=bus,
        session_manager=session_manager,
    )

    message_tool = agent.tools.get("message")
    if isinstance(message_tool, MessageTool):
        message_tool.set_send_callback(deliver_to_channel)

    # Set cron callback (needs agent)

    scheduled_jobs = ScheduledAgentJobs(agent, cron, report=console.print)
    cron.on_job = scheduled_jobs.execute

    def _webui_runtime_model_name() -> str | None:
        return agent.model.strip() or None

    def _webui_refresh_runtime_config() -> None:
        recovery.resume_settings = config.agents.defaults.resume
        agent.refresh_runtime_config()
        agent.context.memory_context_tokens = config.agents.defaults.memory.context_tokens
        agent.context.checkpoint_context_tokens = config.agents.defaults.memory.checkpoint_tokens
        agent.release_archived_runtime = config.agents.defaults.memory.release_archived_runtime
        agent.dream_max_iterations = config.agents.defaults.dream.max_tool_iterations
        agent.dream_model_preset = config.agents.defaults.dream.model_override

    def _webui_skill_state_action(disabled_skills: set[str]) -> None:
        config.agents.defaults.disabled_skills = sorted(disabled_skills)
        agent.context.skills.disabled_skills = set(disabled_skills)
        agent.subagents.tools.disabled_skills = set(disabled_skills)

    # Create channel manager (forwards SessionManager so the WebSocket channel
    # can serve the embedded webui's REST surface).
    channels = ChannelManager(
        config,
        bus,
        session_manager=session_manager,
        cron_service=cron,
        local_trigger_store=trigger_store,
        webui_runtime_model_name=_webui_runtime_model_name,
        webui_context_usage=agent.estimate_session_context_usage,
        webui_maintenance=agent.maintenance,
        webui_refresh_runtime_config=_webui_refresh_runtime_config,
        webui_cron_pending_job_ids=agent.pending_cron_job_ids_for_session,
        webui_local_trigger_pending_ids=agent.pending_local_trigger_ids_for_session,
        webui_static_dist=webui_static_dist,
        webui_mcp_runtime_status=mcp_provider.runtime_status,
        webui_mcp_reload=mcp_provider.reload,
        webui_skill_state_action=_webui_skill_state_action,
        webui_recovery_action=recovery.handle_action,
        webui_subagent_manager=agent.subagents,
        webui_discard_session=agent.discard_session,
        config_path=Path(config_path),
    )

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    hb_cfg = config.agents.defaults.heartbeat
    if hb_cfg.enabled:
        console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")
    else:
        console.print("[yellow]✗[/yellow] Heartbeat: disabled")

    health_listener = HealthListener(
        channels, bus.admission, health_identity, on_listening=_print_gateway_health_endpoint,
    )

    scheduled_jobs.register(config)

    async def run() -> None:
        desktop_activated = asyncio.Event()
        tasks: list[asyncio.Task[Any]] = []
        shutdown_task: asyncio.Task[Any] | None = None
        runtime_tasks: asyncio.Future[list[Any]] | None = None
        startup_complete = False
        shutdown_event = asyncio.Event()
        restore_shutdown_handlers = install_shutdown_handlers(
            asyncio.get_running_loop(),
            shutdown_event,
            tasks,
            console.print,
        )
        try:
            from cirno_server.webui.auth.store import AccountStore
            router_handle = await asyncio.to_thread(AccountStore(gateway_instance.config_path.parent / "state" / "webui-auth.sqlite3").router_handle)
            await ensure_router_session(session_manager, handle=router_handle)
            await agent.subagents.recover_interrupted()
            # Re-read once on first admission to close the watcher subscription window.
            agent.runtime_resolver.invalidate()
            # Recovery must finish before WebSocket and other channels begin
            # accepting new input.  That makes a new user message reliably
            # supersede an old recoverable turn instead of racing its queue.
            await agent.operation_approval.recover()
            await recovery.scan()

            await cron.start()

            async def _run_agent() -> None:
                try:
                    await bus.admission.wait_until_open()
                    await mcp_provider.connect()
                    await agent.run()
                finally:
                    await mcp_provider.aclose()

            tasks.extend(
                [
                    asyncio.create_task(
                        gateway_runtime.wait_for_shutdown_request(shutdown_event),
                        name="cirno-gateway-stop-request",
                    ),
                    asyncio.create_task(
                        watch_config_file(
                            Path(config_path),
                            lambda: agent.invalidate_runtime_config(),
                        ),
                        name="cirno-config-watcher",
                    ),
                    asyncio.create_task(_run_agent(), name="cirno-agent-loop"),
                    asyncio.create_task(channels.start_all(), name="cirno-channels"),
                    asyncio.create_task(
                        run_local_trigger_queue(
                            store=trigger_store,
                            submit_turn=agent.submit_local_trigger_turn,
                            is_channel_enabled=lambda name: channels.get_channel(name) is not None,
                            admission=bus.admission,
                        ),
                        name="cirno-local-triggers",
                    ),
                ]
            )
            from cirno_core.nodes.monitor import monitor_node_jobs
            tasks.append(asyncio.create_task(monitor_node_jobs(), name="cirno-node-jobs"))
            desktop_activated.set()
            if _webui_channel_enabled(config):
                tasks.append(
                    asyncio.create_task(
                        watch_gateway_icon(
                            webui_url,
                            instance=gateway_instance.paths.state_path,
                            activated=desktop_activated,
                        ),
                        name="cirno-dock",
                    )
                )
            if health_server_enabled:
                tasks.append(
                    asyncio.create_task(
                        health_listener.serve(config.server.health_host, port),
                        name="cirno-health-server",
                    )
                )
            if open_browser_url:
                tasks.append(
                    asyncio.create_task(
                        open_when_ready(
                            open_browser_url, ready_url=open_browser_ready_url,
                            fallback_host=config.server.health_host, fallback_port=port,
                            report=console.print,
                        ),
                        name="cirno-open-browser",
                    )
                )
            if webui_dev_server is not None:
                tasks.append(
                    asyncio.create_task(
                        watch_dev_server(webui_dev_server, shutdown_event),
                        name="cirno-webui-dev-server",
                    )
                )
            runtime_tasks = asyncio.gather(*tasks)
            startup_complete = True
            shutdown_task = asyncio.create_task(
                shutdown_event.wait(),
                name="cirno-gateway-shutdown",
            )
            done, _pending = await asyncio.wait(
                {runtime_tasks, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if runtime_tasks in done:
                await runtime_tasks
            else:
                runtime_tasks.cancel()
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        except WebUIDevError:
            raise
        except Exception:
            import traceback

            console.print("\n[red]Error: Cirno stopped unexpectedly[/red]")
            console.print(traceback.format_exc())
            if not startup_complete:
                # Do not report a successful gateway command when startup
                # failed before any runtime task or listener was created.
                raise typer.Exit(1)
        finally:
            try:
                if shutdown_task and not shutdown_task.done():
                    shutdown_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await shutdown_task
                cron.stop()
                # A gateway exit interrupts ownership of active turns; it is
                # not the same as the user stopping a turn.  Keep checkpoints
                # so the next gateway can offer an explicit Continue action.
                agent.preserve_inflight_turns_on_shutdown()
                agent.stop()
                # Cancel runtime tasks first, then deterministically close
                # exec/MCP resources while the event loop is still alive.
                try:
                    await close_runtime(
                        agent,
                        mcp_provider,
                        channels,
                        tasks,
                        runtime_tasks,
                    )
                finally:
                    await bus.drain()
            finally:
                restore_shutdown_handlers()

    with webui_turn_coordinator.connected():
        if health_server_enabled:
            gateway_runtime.publish_health_host(config.server.health_host)
        asyncio.run(run())
