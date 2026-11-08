"""Web searches anysearch."""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext

_ANYSEARCH_SEARCH_API_URL = "https://api.anysearch.com/v1/search"


async def search(context: SearchContext, query: str, n: int) -> str:
    """Search via AnySearch (https://anysearch.com).

    An API key is optional: without one the request uses AnySearch's
    anonymous quota with lower rate limits, so the provider works out of
    the box.
    """
    api_key = context.config.api_key or os.environ.get("ANYSEARCH_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": context.user_agent,
        "X-Anysearch-Client": "cirno/1.0.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                _ANYSEARCH_SEARCH_API_URL,
                headers=headers,
                json={"query": query, "max_results": n},
                timeout=float(context.config.timeout),
            )
            r.raise_for_status()
        data = cast(dict[str, Any], r.json().get("data", {}))
        results = cast(list[object], data.get("results", []))
        items: list[dict[str, Any]] = [
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("content") or result.get("snippet", ""),
            }
            for result_value in results
            if isinstance(result_value, dict)
            for result in (cast(dict[str, Any], result_value),)
        ]
        return _format_results(query, items, n)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return ToolResult.error(
                "Error: AnySearch search rate limited. Try again later or reduce search frequency."
            )
        return ToolResult.error(f"Error: AnySearch search failed ({e.response.status_code}): {e}")
    except Exception as e:
        return ToolResult.error(f"Error: AnySearch search failed: {e}")
