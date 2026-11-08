"""Web searches brave."""

from __future__ import annotations

import asyncio
import os

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger


async def search(context: SearchContext, query: str, n: int) -> str:
    api_key = context.config.api_key or os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        logger.warning("BRAVE_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": context.user_agent,
        }
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r: httpx.Response | None = None
            for attempt in range(2):
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers=headers,
                    timeout=10.0,
                )
                if r.status_code != 429:
                    break
                if attempt == 0:
                    logger.warning("Brave search rate limited; retrying once in 1.0s")
                    await asyncio.sleep(1.0)
            assert r is not None
            r.raise_for_status()
        items = [
            {
                "title": x.get("title", ""),
                "url": x.get("url", ""),
                "content": x.get("description", ""),
            }
            for x in r.json().get("web", {}).get("results", [])
        ]
        return _format_results(query, items, n)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return ToolResult.error(
                "Error: Brave search rate limited after retry. "
                "Retry later or reduce consecutive web_search calls."
            )
        return ToolResult.error(f"Error: {e}")
    except Exception as e:
        return ToolResult.error(f"Error: {e}")
