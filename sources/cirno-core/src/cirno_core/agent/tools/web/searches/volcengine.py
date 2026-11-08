"""Web searches volcengine."""

from __future__ import annotations

import os
import re
from typing import Any, cast

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.content import _format_results
from cirno_core.agent.tools.web.searches import duckduckgo
from loguru import logger

_VOLCENGINE_SEARCH_API_URL = "https://open.feedcoopapi.com/search_api/web_search"


_VOLCENGINE_TRAFFIC_TAG = "cirno"


_VOLCENGINE_TIME_RANGES = {"OneDay", "OneWeek", "OneMonth", "OneYear"}


_VOLCENGINE_DATE_RANGE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}$")


def _normalize_volcengine_time_range(value: Any) -> str | None:
    if value is None:
        return None
    time_range = str(value).strip()
    if not time_range:
        return None
    if time_range in _VOLCENGINE_TIME_RANGES or _VOLCENGINE_DATE_RANGE_RE.fullmatch(time_range):
        return time_range
    raise ValueError(
        "timeRange must be OneDay, OneWeek, OneMonth, OneYear, or YYYY-MM-DD..YYYY-MM-DD"
    )


def _normalize_volcengine_auth_level(value: Any) -> int | None:
    if value is None:
        return None
    try:
        auth_level = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("authLevel must be 0 or 1") from exc
    if auth_level not in {0, 1}:
        raise ValueError("authLevel must be 0 or 1")
    return auth_level


async def search(
    context: SearchContext,
    query: str,
    n: int,
    *,
    time_range: str | None = None,
    auth_level: int | None = None,
    query_rewrite: bool | None = None,
) -> str:
    api_key = (
        context.config.api_key
        or os.environ.get("VOLCENGINE_SEARCH_API_KEY", "")
        or os.environ.get("WEB_SEARCH_API_KEY", "")
    )
    if not api_key:
        logger.warning(
            "VOLCENGINE_SEARCH_API_KEY/WEB_SEARCH_API_KEY not set, falling back to DuckDuckGo"
        )
        return await duckduckgo.search(context, query, n)

    try:
        normalized_time_range = _normalize_volcengine_time_range(time_range) if time_range else None
        normalized_auth_level = (
            _normalize_volcengine_auth_level(auth_level) if auth_level is not None else None
        )
    except ValueError as e:
        return ToolResult.error(f"Error: {e}")

    body: dict[str, Any] = {
        "Query": query,
        "SearchType": "web",
        "Count": n,
        "NeedSummary": True,
    }
    if normalized_time_range:
        body["TimeRange"] = normalized_time_range
    if normalized_auth_level is not None:
        body["Filter"] = {"AuthInfoLevel": normalized_auth_level}
    if query_rewrite:
        body["QueryControl"] = {"QueryRewrite": True}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": context.user_agent,
        "X-Traffic-Tag": _VOLCENGINE_TRAFFIC_TAG,
    }
    try:
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r = await client.post(
                _VOLCENGINE_SEARCH_API_URL,
                headers=headers,
                json=body,
                timeout=float(context.config.timeout),
            )
            r.raise_for_status()
        data = cast(dict[str, Any], r.json())
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return ToolResult.error(
                "Error: Volcengine search rate limited. Try again later or reduce search frequency."
            )
        return ToolResult.error(f"Error: Volcengine search failed ({e.response.status_code}): {e}")
    except Exception as e:
        return ToolResult.error(f"Error: Volcengine search failed: {e}")

    response_metadata = cast(
        dict[str, Any],
        data.get("ResponseMetadata") or {},
    )
    error = response_metadata.get("Error") or data.get("Error") or data.get("error")
    if error:
        if isinstance(error, dict):
            error = cast(dict[str, Any], error)
            code = error.get("Code") or error.get("code") or "unknown"
            message = error.get("Message") or error.get("message") or error
            return ToolResult.error(f"Error: Volcengine search error {code}: {message}")
        return ToolResult.error(f"Error: Volcengine search error: {error}")

    result = cast(dict[str, Any], data.get("Result") or data)
    web_results = cast(
        list[object],
        result.get("WebResults") or result.get("webResults") or result.get("results") or [],
    )
    items: list[dict[str, Any]] = []
    for item_value in web_results:
        if not isinstance(item_value, dict):
            continue
        item = cast(dict[str, Any], item_value)
        meta_parts = [
            str(part)
            for part in (
                item.get("SiteName") or item.get("siteName") or item.get("Site"),
                item.get("AuthInfoDes") or item.get("authInfoDes"),
                item.get("PublishTime") or item.get("publishTime"),
            )
            if part
        ]
        summary = cast(
            str,
            (
                item.get("Summary")
                or item.get("summary")
                or item.get("Snippet")
                or item.get("snippet")
                or item.get("Content")
                or item.get("content")
                or ""
            ),
        )
        content = "\n".join(part for part in (" | ".join(meta_parts), summary) if part)
        items.append(
            {
                "title": item.get("Title") or item.get("title") or "",
                "url": item.get("Url") or item.get("URL") or item.get("url") or "",
                "content": content,
            }
        )

    return _format_results(query, items, n)
