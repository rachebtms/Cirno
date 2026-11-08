"""Web searches serper."""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger


async def search(context: SearchContext, query: str, n: int) -> str:
    """Search via Serper.dev (Google Search API)."""
    api_key = context.config.api_key or os.environ.get("SERPER_API_KEY", "")
    if not api_key:
        logger.warning("SERPER_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "User-Agent": context.user_agent,
        }
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "num": n},
                timeout=float(context.config.timeout),
            )
            r.raise_for_status()
        data = cast(dict[str, Any], r.json())
        organic = cast(list[object], data.get("organic", []))
        items: list[dict[str, Any]] = [
            {
                "title": result.get("title", ""),
                "url": result.get("link", ""),
                "content": result.get("snippet", ""),
            }
            for result_value in organic
            if isinstance(result_value, dict)
            for result in (cast(dict[str, Any], result_value),)
        ]
        return _format_results(query, items, n)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return ToolResult.error(
                "Error: Serper search rate limited. Try again later or reduce search frequency."
            )
        return ToolResult.error(f"Error: Serper search failed ({e.response.status_code}): {e}")
    except Exception as e:
        return ToolResult.error(f"Error: Serper search failed: {e}")
