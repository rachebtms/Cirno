"""MCP connector."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import AsyncExitStack, suppress
from typing import TYPE_CHECKING, Any

import httpx
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.network import NetworkConfig
from cirno_core.security.network import (
    validate_url_target,
)
from cirno_core.utils.cancellation import shield_and_drain, task_is_cancelling
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.tools.mcp_oauth import MCPOAuthHandlers
    from cirno_core.config.tools import MCPServerConfig

from cirno_core.agent.tools.mcp.connections import close_mcp_connections, OwnedMCPConnection
from cirno_core.agent.tools.mcp.contracts import MCPConnection
from cirno_core.agent.tools.mcp.discovery import register_capabilities
from cirno_core.agent.tools.mcp.errors import _log_mcp_connection_failure, _redact_url
from cirno_core.agent.tools.mcp.http import (
    _HTTP_READ_TIMEOUT,
    _HTTP_TIMEOUT,
    _pinned_transport_kwargs,
    _probe_http_url,
    _validate_mcp_request_url,
)
from cirno_core.agent.tools.mcp.progress import _filter_malformed_mcp_progress_notifications
from cirno_core.agent.tools.mcp.registrations import _unregister_server_tools
from cirno_core.agent.tools.mcp.stdio import _normalize_windows_stdio_command


async def connect_mcp_servers(
    mcp_servers: dict[str, MCPServerConfig],
    registry: ToolRegistry,
    *,
    oauth_handlers: Mapping[str, MCPOAuthHandlers] | None = None,
    network: NetworkConfig | None = None,
) -> dict[str, MCPConnection]:
    """Connect to configured MCP servers and register their tools, resources, prompts.

    Returns one connection handle per server.  Each handle keeps the task that
    entered the MCP SDK contexts alive so reconnect and shutdown can close
    AnyIO cancel scopes from their owning task.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    # Stack-exit failures are logged outside open_single_server; retain the exact
    # selected value there too, including credentials resolved from environment refs.
    selected_proxies: dict[str, str | None] = {}

    async def open_single_server(
        name: str, cfg: MCPServerConfig, server_stack: AsyncExitStack
    ) -> bool:
        try:
            transport_type = cfg.type
            if not transport_type:
                if cfg.command:
                    transport_type = "stdio"
                elif cfg.url:
                    transport_type = (
                        "sse" if cfg.url.rstrip("/").endswith("/sse") else "streamableHttp"
                    )
                else:
                    logger.warning("MCP server '{}': no command or url configured, skipping", name)
                    return False

            if transport_type in {"sse", "streamableHttp"}:
                ok, error = validate_url_target(cfg.url)
                if not ok:
                    logger.warning(
                        "MCP server '{}': blocked unsafe URL {} ({})",
                        name,
                        _redact_url(cfg.url),
                        error,
                    )
                    return False

            if cfg.use_proxy and transport_type == "stdio":
                raise ValueError("The shared proxy is available for HTTP and SSE MCP connections")
            proxy = (network or NetworkConfig()).resolve_proxy(cfg.use_proxy)
            selected_proxies[name] = proxy
            oauth_auth: httpx.Auth | None = None
            if cfg.auth == "oauth":
                if transport_type not in {"sse", "streamableHttp"}:
                    logger.warning(
                        "MCP server '{}': OAuth requires an SSE or Streamable HTTP transport",
                        name,
                    )
                    return False
                from cirno_core.agent.tools.mcp_oauth import (
                    MCPAuthorizationRequiredError,
                    create_mcp_oauth_auth,
                )

                try:
                    oauth_auth = await create_mcp_oauth_auth(
                        name,
                        cfg.url,
                        (oauth_handlers or {}).get(name),
                    )
                except MCPAuthorizationRequiredError:
                    logger.info("MCP server '{}': waiting for browser authorization", name)
                    return False

            if transport_type == "stdio":
                command, args, env = _normalize_windows_stdio_command(
                    cfg.command,
                    cfg.args,
                    cfg.env or None,
                )
                params = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env,
                    cwd=cfg.cwd or None,
                )
                read, write = await server_stack.enter_async_context(stdio_client(params))
            elif transport_type == "sse":
                if not await _probe_http_url(cfg.url, proxy=proxy):
                    logger.warning(
                        "MCP server '{}': {} unreachable, skipping", name, _redact_url(cfg.url)
                    )
                    return False

                def httpx_client_factory(
                    headers: dict[str, str] | None = None,
                    timeout: httpx.Timeout | None = None,
                    auth: httpx.Auth | None = None,
                ) -> httpx.AsyncClient:
                    merged_headers = {
                        "Accept": "application/json, text/event-stream",
                        **(cfg.headers or {}),
                        **(headers or {}),
                    }
                    return httpx.AsyncClient(
                        headers=merged_headers or None,
                        event_hooks={"request": [_validate_mcp_request_url]},
                        follow_redirects=True,
                        timeout=timeout,
                        auth=auth,
                        **_pinned_transport_kwargs(proxy),
                    )

                sse_kwargs: dict[str, Any] = {
                    "httpx_client_factory": httpx_client_factory,
                }
                if oauth_auth is not None:
                    sse_kwargs["auth"] = oauth_auth
                read, write = await server_stack.enter_async_context(
                    sse_client(cfg.url, **sse_kwargs)
                )
            elif transport_type == "streamableHttp":
                if not await _probe_http_url(cfg.url, proxy=proxy):
                    logger.warning(
                        "MCP server '{}': {} unreachable, skipping", name, _redact_url(cfg.url)
                    )
                    return False

                http_client_kwargs: dict[str, Any] = {
                    "headers": cfg.headers or None,
                    "event_hooks": {"request": [_validate_mcp_request_url]},
                    "follow_redirects": True,
                    # Read must outlast the tool call itself; otherwise a slow tool
                    # fails with ReadTimeout before tool_timeout is reached.
                    "timeout": httpx.Timeout(
                        _HTTP_TIMEOUT,
                        connect=10.0,
                        read=max(_HTTP_READ_TIMEOUT, cfg.tool_timeout),
                    ),
                    **_pinned_transport_kwargs(proxy),
                }
                if oauth_auth is not None:
                    http_client_kwargs["auth"] = oauth_auth
                http_client = await server_stack.enter_async_context(
                    httpx.AsyncClient(**http_client_kwargs)
                )
                read, write, _ = await server_stack.enter_async_context(
                    streamable_http_client(cfg.url, http_client=http_client)
                )
            else:
                logger.warning("MCP server '{}': unknown transport type '{}'", name, transport_type)
                return False

            read = _filter_malformed_mcp_progress_notifications(read, name)
            session = await server_stack.enter_async_context(ClientSession(read, write))
            initialization = await session.initialize()

            registered_count = await register_capabilities(
                session,
                initialization.capabilities,
                name,
                cfg,
                registry,
            )

            logger.info(
                "MCP server '{}': connected, {} capabilities registered", name, registered_count
            )
            return True

        except Exception as e:
            hint = ""
            text = str(e).lower()
            if any(
                marker in text
                for marker in (
                    "parse error",
                    "invalid json",
                    "unexpected token",
                    "jsonrpc",
                    "content-length",
                )
            ):
                hint = (
                    " Hint: this looks like stdio protocol pollution. Make sure the MCP server writes "
                    "only JSON-RPC to stdout and sends logs/debug output to stderr instead."
                )
            _log_mcp_connection_failure(name, e, hint, proxy=selected_proxies.get(name))
            return False

    async def connect_single_server(
        name: str, cfg: MCPServerConfig
    ) -> tuple[str, MCPConnection | None]:
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[bool] = loop.create_future()
        close_requested = asyncio.Event()

        async def own_connection() -> None:
            try:
                async with AsyncExitStack() as stack:
                    connected = await open_single_server(name, cfg, stack)
                    if not ready.done():
                        ready.set_result(connected)
                    if connected:
                        await close_requested.wait()
            except BaseException as exc:
                if not ready.done():
                    ready.set_exception(exc)
                raise

        owner = asyncio.create_task(own_connection(), name=f"mcp:{name}")
        connection = OwnedMCPConnection(owner, close_requested)
        try:
            connected = await ready
        except BaseException as exc:
            close_requested.set()
            owner.cancel()
            with suppress(BaseException):
                await shield_and_drain(owner)
            if isinstance(exc, asyncio.CancelledError) and not task_is_cancelling():
                logger.warning("MCP server '{}': connection cancelled by server/SDK", name)
                return name, None
            raise
        if not connected:
            await connection.aclose()
            return name, None
        return name, connection

    server_stacks: dict[str, MCPConnection] = {}
    attempted_names: list[str] = []

    try:
        for name, cfg in mcp_servers.items():
            attempted_names.append(name)
            try:
                result = await connect_single_server(name, cfg)
            except Exception as e:
                _log_mcp_connection_failure(name, e, proxy=selected_proxies.get(name))
                continue
            if result[1] is not None:
                server_stacks[result[0]] = result[1]
    except BaseException:
        # Callers can bound readiness/reload with a timeout. If cancellation
        # interrupts a later server, ownership of earlier connections has not
        # transferred yet, so roll the whole batch back before propagating it.
        for name in attempted_names:
            _unregister_server_tools(registry, name)
        try:
            await close_mcp_connections(server_stacks)
        except BaseException as cleanup_exc:
            logger.warning("MCP batch rollback cleanup failed ({})", type(cleanup_exc).__name__)
        raise

    return server_stacks
