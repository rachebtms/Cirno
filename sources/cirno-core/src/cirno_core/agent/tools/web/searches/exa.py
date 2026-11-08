"""Web searches exa."""

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
    api_key = context.config.api_key or os.environ.get("EXA_API_KEY", "")
    if not api_key:
        logger.warning("EXA_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": context.user_agent,
        }
        body = {
            "query": query,
            "numResults": n,
            "contents": {"highlights": True},
        }
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                "https://api.exa.ai/search",
                headers=headers,
                json=body,
                timeout=float(context.config.timeout),
            )
            r.raise_for_status()
        data = cast(dict[str, Any], r.json())
        items: list[dict[str, Any]] = []
        for result_value in cast(list[object], data.get("results", [])):
            if not isinstance(result_value, dict):
                continue
            result = cast(dict[str, Any], result_value)
            highlights: Any = result.get("highlights") or []
            if isinstance(highlights, list):
                content = "\n".join(
                    str(highlight) for highlight in cast(list[object], highlights) if highlight
                )
            else:
                content = str(highlights)
            if not content:
                content = str(result.get("summary") or result.get("text") or "")[:500]
            items.append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": content,
                }
            )
        return _format_results(query, items, n)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return ToolResult.error(
                "Error: Exa search rate limited. Try again later or reduce search frequency."
            )
        return ToolResult.error(f"Error: Exa search failed ({e.response.status_code}): {e}")
    except Exception as e:
        return ToolResult.error(f"Error: Exa search failed: {e}")
