"""Web searches keenable."""

from __future__ import annotations

import os

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext

_KEENABLE_SEARCH_API_URL = "https://api.keenable.ai/v1/search"


async def search(context: SearchContext, query: str, n: int) -> str:
    api_key = context.config.api_key or os.environ.get("KEENABLE_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": context.user_agent,
        "X-Keenable-Title": "cirno",
    }
    # Without a key, the token-less /public endpoint serves the free tier.
    url = _KEENABLE_SEARCH_API_URL
    if api_key:
        headers["X-API-Key"] = api_key
    else:
        url += "/public"
    try:
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                url,
                headers=headers,
                json={"query": query},
                timeout=float(context.config.timeout),
            )
            r.raise_for_status()
        items = [
            {
                "title": x.get("title", ""),
                "url": x.get("url", ""),
                "content": x.get("snippet") or x.get("description", ""),
            }
            for x in r.json().get("results", [])
        ]
        return _format_results(query, items, n)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return ToolResult.error(
                "Error: Keenable search rate limited. Try again later or reduce search frequency."
            )
        return ToolResult.error(f"Error: Keenable search failed ({e.response.status_code}): {e}")
    except Exception as e:
        return ToolResult.error(f"Error: Keenable search failed: {e}")
