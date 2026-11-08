"""Web searches jina."""

from __future__ import annotations

import os
from urllib.parse import quote

import httpx
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger


async def search(context: SearchContext, query: str, n: int) -> str:
    api_key = context.config.api_key or os.environ.get("JINA_API_KEY", "")
    if not api_key:
        logger.warning("JINA_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": context.user_agent,
        }
        encoded_query = quote(query, safe="")
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.get(
                f"https://s.jina.ai/{encoded_query}",
                headers=headers,
                timeout=15.0,
            )
            r.raise_for_status()
        data = r.json().get("data", [])[:n]
        items = [
            {
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "content": d.get("content", "")[:500],
            }
            for d in data
        ]
        return _format_results(query, items, n)
    except Exception as e:
        logger.warning(
            "Jina search failed ({}), falling back to DuckDuckGo",
            e if tool_log_content_allowed() else type(e).__name__,
        )
        return await duckduckgo.search(context, query, n)
