"""MCP errors."""

from __future__ import annotations

import traceback
import urllib.parse
from typing import cast

import httpx
from cirno_core.agent.tools.context import tool_log_content_allowed
from loguru import logger

_TRANSIENT_EXC_NAMES: frozenset[str] = frozenset(
    (
        "ClosedResourceError",
        "BrokenResourceError",
        "EndOfStream",
        "BrokenPipeError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "ConnectionError",
    )
)


def _is_transient(exc: BaseException) -> bool:
    """Check if an exception looks like a transient connection error."""
    return type(exc).__name__ in _TRANSIENT_EXC_NAMES


def _is_transient_connection_failure(exc: BaseException) -> bool:
    if isinstance(exc, BaseExceptionGroup):
        group = cast(BaseExceptionGroup[BaseException], exc)
        return bool(group.exceptions) and all(
            _is_transient_connection_failure(nested) for nested in group.exceptions
        )
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or _is_transient(exc)


def _log_mcp_connection_failure(
    name: str,
    exc: BaseException,
    hint: str = "",
    *,
    proxy: str | None = None,
) -> None:
    exception: Exception | bool = False
    if tool_log_content_allowed():
        details = "".join(
            traceback.TracebackException.from_exception(
                exc,
                capture_locals=False,
            ).format()
        )
        if proxy:
            for value in (proxy, urllib.parse.unquote(proxy)):
                details = details.replace(value, _redact_url(proxy))
            # Match userinfo only with its URL delimiter, never isolated short
            # credentials that could rewrite exception types or stack text.
            userinfo = urllib.parse.urlsplit(proxy).netloc.rpartition("@")[0]
            if userinfo:
                for value in (userinfo, urllib.parse.unquote(userinfo)):
                    details = details.replace(f"{value}@", "[redacted]@")
        # Keep exception-aware sinks, but never give Loguru live frames or a raw
        # exception chain: diagnose=True would render credential-bearing locals.
        exception = Exception("\n" + details.rstrip())
    if _is_transient_connection_failure(exc):
        logger.warning("MCP server '{}': transient connection failure", name)
        logger.opt(exception=exception).debug(
            "MCP server '{}' transient connection failure details", name
        )
        return
    logger.opt(exception=exception).error("MCP server '{}': failed to connect: {}", name, hint)


def _is_session_terminated(exc: BaseException) -> bool:
    """Return True when the MCP SDK reports a dead client session."""
    if _is_transient(exc):
        return True
    messages = [str(exc)]
    error = getattr(exc, "error", None)
    if error is not None:
        messages.append(str(getattr(error, "message", "")))
    return any(
        marker in message.lower()
        for marker in ("session terminated", "connection closed")
        for message in messages
    )


def _redact_url(url: str) -> str:
    """Strip credentials and query/fragment before logging an MCP URL.

    Server URLs may embed secrets (``https://user:token@host/sse`` or a
    ``?token=`` query). Some deployments also put opaque tokens in the path, so
    log only the origin and a path placeholder.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        hostname = parts.hostname or ""
        netloc = f"[{hostname}]" if ":" in hostname else hostname
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        path = "/..." if parts.path and parts.path != "/" else parts.path
        return urllib.parse.urlunsplit((parts.scheme, netloc, path, "", ""))
    except Exception:
        return "<redacted-url>"
