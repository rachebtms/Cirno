"""Web searches tavily."""

from __future__ import annotations

import os

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger


async def search(context: SearchContext, query: str, n: int) -> str:
    api_key = context.config.api_key or os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {api_key}", "User-Agent": context.user_agent},
                json={"query": query, "max_results": n},
                timeout=15.0,
            )
            r.raise_for_status()
        return _format_results(query, r.json().get("results", []), n)
    except Exception as e:
        return ToolResult.error(f"Error: {e}")
