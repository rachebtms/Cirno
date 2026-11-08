"""MCP http."""

from __future__ import annotations

import asyncio
import urllib.parse
from contextlib import suppress
from typing import Any

import httpx
from cirno_core.agent.tools.mcp.errors import _redact_url
from cirno_core.security.network import (
    PinnedDNSAsyncTransport,
    env_proxy_applies_to_url,
    httpx_env_proxy_mounts,
    resolve_url_target,
    validate_url_target,
)

_HTTP_TIMEOUT = 30.0


_HTTP_READ_TIMEOUT = 300.0


async def _probe_http_url(url: str, timeout: float = 3.0, *, proxy: str | None = None) -> bool:
    """Quick TCP probe to check if an HTTP MCP server is reachable.

    Avoids entering ``streamable_http_client`` / ``sse_client`` when the port is
    closed — those transports use anyio task groups whose cleanup can raise
    ``RuntimeError`` / ``ExceptionGroup`` that escape the caller's try/except
    and crash the event loop.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if not port:
        port = 443 if parsed.scheme == "https" else 80
    ok, _, resolved_ips = resolve_url_target(url)
    if not ok:
        return False
    if proxy or env_proxy_applies_to_url(url):
        return True
    for target_host in resolved_ips or (host,):
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, port),
                timeout=timeout,
            )
            writer.close()
            with suppress(OSError, asyncio.TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), timeout=0.2)
            return True
        except (OSError, asyncio.TimeoutError):
            continue
    return False


def _pinned_transport_kwargs(proxy: str | None = None) -> dict[str, Any]:
    if proxy:
        return {"transport": httpx.AsyncHTTPTransport(proxy=proxy), "trust_env": False}
    kwargs: dict[str, Any] = {"transport": PinnedDNSAsyncTransport()}
    mounts = httpx_env_proxy_mounts()
    if mounts:
        kwargs["mounts"] = mounts
    return kwargs


async def _validate_mcp_request_url(request: httpx.Request) -> None:
    """Validate each outgoing MCP HTTP request, including redirect targets."""
    ok, error = validate_url_target(str(request.url))
    if not ok:
        raise httpx.RequestError(
            f"Blocked unsafe MCP URL {_redact_url(str(request.url))} ({error})",
            request=request,
        )
