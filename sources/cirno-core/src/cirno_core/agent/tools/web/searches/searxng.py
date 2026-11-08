"""Web searches searxng."""

from __future__ import annotations

import os

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.network import _validate_url
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger


async def search(context: SearchContext, query: str, n: int) -> str:
    base_url = (context.config.base_url or os.environ.get("SEARXNG_BASE_URL", "")).strip()
    if not base_url:
        logger.warning("SEARXNG_BASE_URL not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    endpoint = f"{base_url.rstrip('/')}/search"
    is_valid, error_msg = _validate_url(endpoint)
    if not is_valid:
        return ToolResult.error(f"Error: invalid SearXNG URL: {error_msg}")
    try:
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.get(
                endpoint,
                params={"q": query, "format": "json"},
                headers={"User-Agent": context.user_agent},
                timeout=10.0,
            )
            r.raise_for_status()
        return _format_results(query, r.json().get("results", []), n)
    except Exception as e:
        return ToolResult.error(f"Error: {e}")
