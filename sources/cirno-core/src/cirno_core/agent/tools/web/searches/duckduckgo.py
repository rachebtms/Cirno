"""Web searches duckduckgo."""

from __future__ import annotations

import asyncio
import time
from threading import Event, Lock
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from ddgs.exceptions import DDGSException
from ddgs.exceptions import TimeoutException as DDGSTimeoutException
from loguru import logger

_DDGS_LOCK = Lock()


def _request(context: SearchContext, query: str, n: int, cancelled: Event, deadline: float) -> list[dict[str, Any]]:
    from ddgs import DDGS

    # A stopped asyncio call can leave its synchronous request running in a thread.
    with _DDGS_LOCK:
        if cancelled.is_set():
            return []

        def attempt() -> list[dict[str, Any]]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Search deadline expired")
            client = cast(Any, DDGS)(timeout=min(10, remaining), proxy=context.proxy)
            return client.text(query, max_results=n)

        try:
            return attempt()
        except DDGSException:
            # Searching is read-only. One serial retry handles intermittent
            # engine failures without extending the caller's total deadline.
            if deadline - time.monotonic() <= 0.5:
                raise
            if cancelled.wait(0.5):
                return []
            return attempt()


def _failure_detail(error: Exception, context: SearchContext) -> str:
    detail = str(error)
    secrets = [context.config.api_key, context.proxy]
    if context.proxy:
        password = urlsplit(context.proxy).password
        secrets.extend([password, unquote(password) if password else None])
    for secret in secrets:
        if secret:
            detail = detail.replace(secret, "[redacted]")
    return f"{type(error).__name__}: {detail[:1000]}"


async def search(context: SearchContext, query: str, n: int) -> str:
    cancelled = Event()
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_request, context, query, n, cancelled, time.monotonic() + context.config.timeout),
            timeout=context.config.timeout,
        )
        raw_items = cast(list[dict[str, Any]], raw)
        items: list[dict[str, Any]] = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
            for r in raw_items
        ]
        return _format_results(query, items, n)
    except Exception as e:
        detail = _failure_detail(e, context)
        logger.warning(
            "DuckDuckGo search failed: {}",
            detail if tool_log_content_allowed() else type(e).__name__,
        )
        if isinstance(e, TimeoutError):
            return ToolResult.error(
                "Error: Web search timed out while waiting for ddgs. "
                "No usable search result was obtained before the tool deadline; "
                "matching-page availability is unknown."
            )
        if isinstance(e, DDGSTimeoutException):
            return ToolResult.error(
                "Error: Web search unavailable (ddgs reported a timeout). "
                "No usable search result was obtained; matching-page availability is unknown. "
                f"Library detail: {detail}"
            )
        if isinstance(e, DDGSException):
            return ToolResult.error(
                "Error: Web search unavailable (ddgs; cause unknown). "
                "No usable search result was obtained. The search library did not expose "
                "a reliable HTTP cause; this does not establish that no matching pages exist. "
                f"Library detail: {detail}"
            )
        return ToolResult.error(f"Error: DuckDuckGo search failed ({detail})")
    finally:
        cancelled.set()
