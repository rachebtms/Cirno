"""Web searches olostep."""

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
    try:
        from olostep import (  # pyright: ignore[reportMissingImports, reportMissingTypeStubs]
            AsyncOlostep,  # pyright: ignore[reportUnknownVariableType]
            Olostep_BaseError,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
        )
    except ImportError:
        return ToolResult.error(
            "Error: Olostep support is not installed. Install Olostep support in Settings → Web search."
        )
    async_olostep = cast(Any, AsyncOlostep)
    olostep_base_error = cast(type[Exception], Olostep_BaseError)
    api_key = context.config.api_key or os.environ.get("OLOSTEP_API_KEY", "")
    if not api_key:
        logger.warning("OLOSTEP_API_KEY not set, falling back to DuckDuckGo")
        return await duckduckgo.search(context, query, n)
    try:
        async with async_olostep(api_key=api_key) as client:
            if context.proxy:
                transport = getattr(client, "_transport", None)
                http_client = getattr(transport, "_client", None)
                if transport is not None and isinstance(http_client, httpx.AsyncClient):
                    await http_client.aclose()
                    transport._client = httpx.AsyncClient(  # type: ignore[attr-defined]
                        proxy=context.proxy,
                        headers=dict(http_client.headers),
                        timeout=http_client.timeout,
                        limits=httpx.Limits(
                            max_keepalive_connections=100,
                            max_connections=200,
                        ),
                        http2=True,
                    )
            result: Any = await client.answers.create(task=query)

        sources = cast(list[Any], getattr(result, "sources", None) or [])
        source_lines: list[str] = []
        for i, source_value in enumerate(sources[:n], 1):
            source: Any = source_value
            if isinstance(source, dict):
                source_dict = cast(dict[str, Any], source)
                title = source_dict.get("title", "")
                url = source_dict.get("url", "")
            else:
                title = getattr(source, "title", "")
                url = getattr(source, "url", "")
            if title and url:
                source_lines.append(f"{i}. {title} — {url}")
            elif url:
                source_lines.append(f"{i}. {url}")
            elif title:
                source_lines.append(f"{i}. {title}")

        answer_text = getattr(result, "answer", "") or ""
        items = [
            {
                "title": answer_text or "Olostep answer",
                "url": "",
                "content": "\n".join(source_lines),
            }
        ]
        return _format_results(query, items, n)
    except olostep_base_error as e:
        return ToolResult.error(f"Error: Olostep search error: {type(e).__name__}: {e}")
    except Exception as e:
        return ToolResult.error(f"Error: Olostep search error: {type(e).__name__}: {e}")
