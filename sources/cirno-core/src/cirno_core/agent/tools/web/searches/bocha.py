"""Web searches bocha."""

from __future__ import annotations

import os
from typing import Any, cast

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger

_BOCHA_SEARCH_API_URL = "https://api.bochaai.com/v1/web-search"


async def search(context: SearchContext, query: str, n: int, freshness: str = "noLimit") -> str:
    api_key = context.config.api_key or os.environ.get("BOCHA_API_KEY", "")
    if not api_key:
        logger.warning("BOCHA_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if context.user_agent:
            headers["User-Agent"] = context.user_agent
        payload = {
            "query": query,
            "freshness": freshness,
            "summary": True,
            "count": n,
        }
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                _BOCHA_SEARCH_API_URL,
                headers=headers,
                json=payload,
                timeout=context.config.timeout,
            )
            if r.status_code == 429:
                return ToolResult.error(
                    "Error: Bocha search rate-limited (HTTP 429). Wait and retry."
                )
            r.raise_for_status()
        data = cast(dict[str, Any], r.json())
        wrapped_data = data.get("data")
        result_data = cast(dict[str, Any], wrapped_data) if isinstance(wrapped_data, dict) else data
        web_pages_data = cast(
            dict[str, Any],
            result_data.get("webPages", {}),
        )
        web_pages = cast(list[dict[str, Any]], web_pages_data.get("value", []))
        items: list[dict[str, Any]] = [
            {
                "title": x.get("name", ""),
                "url": x.get("url", ""),
                "content": x.get("summary", "") or x.get("snippet", ""),
            }
            for x in web_pages
        ]
        return _format_results(query, items, n)
    except httpx.HTTPStatusError as e:
        return ToolResult.error(
            f"Error: Bocha search HTTP {e.response.status_code}: {e.response.text[:200]}"
        )
    except Exception as e:
        return ToolResult.error(f"Error: {e}")
