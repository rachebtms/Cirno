"""Web searches deepseek."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import httpx
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.agent.tools.web.content import _format_results, _normalize, _strip_tags
from cirno_core.agent.tools.web.context import SearchContext
from loguru import logger

_DEEPSEEK_SEARCH_API_URL = "https://api.deepseek.com/v1/tools/search"


_DEEPSEEK_MAX_QUERY_CHARS = 128


_DEEPSEEK_MAX_RESULTS = 50


_DEEPSEEK_MAX_SUMMARY_CHARS = 500


_DEEPSEEK_ERROR_DETAIL_MAX_CHARS = 300


_DEEPSEEK_RETRY_DELAY_S = 1.0


def _deepseek_is_retryable(status_code: int) -> bool:
    """Transient statuses: 408, 429 and 5xx. Every other 4xx needs a new request."""
    return status_code in {408, 429} or status_code >= 500


def _deepseek_text(value: object) -> str:
    """Coerce an optional API string field, tolerating null and non-strings."""
    return value.strip() if isinstance(value, str) else ""


def _deepseek_error_detail(response: httpx.Response) -> str:
    """Read ``error.message`` from the OpenAI-compatible error envelope.

    Returns plain text: the message is tag-stripped and whitespace-collapsed
    because the upstream body is untrusted and is echoed into the model
    context. Nothing from the request headers is logged or returned.
    """
    try:
        payload: object = response.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    error: object = cast(dict[str, object], payload).get("error")
    if not isinstance(error, dict):
        return ""
    message: object = cast(dict[str, object], error).get("message")
    if not isinstance(message, str):
        return ""
    return _normalize(_strip_tags(message))[:_DEEPSEEK_ERROR_DETAIL_MAX_CHARS]


async def search(context: SearchContext, query: str, n: int) -> str:
    """Search via the DeepSeek Search API.

    This is a standalone search backend (``POST /v1/tools/search``) and is
    unrelated to DeepSeek models' provider-hosted search: it never injects
    a ``web_search`` tool into a chat completion request.
    """
    api_key = context.config.api_key
    if not api_key:
        return ToolResult.error(
            "Error: DeepSeek search requires an API key. Set tools.web.search.apiKey."
        )

    normalized_query = query.strip()
    if not normalized_query:
        return ToolResult.error("Error: DeepSeek search requires a non-blank query.")
    if len(normalized_query) > _DEEPSEEK_MAX_QUERY_CHARS:
        return ToolResult.error(
            f"Error: DeepSeek search accepts at most {_DEEPSEEK_MAX_QUERY_CHARS} Unicode characters. "
            "Shorten or split the query while preserving its search operators."
        )
    payload = {
        "query": normalized_query,
        "count": min(max(n, 1), _DEEPSEEK_MAX_RESULTS),
        # Keep full page bodies out of the model's context; summaries suffice.
        "need_content": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": context.user_agent,
    }
    try:
        async with httpx.AsyncClient(proxy=context.proxy) as client:
            r: httpx.Response | None = None
            for attempt in range(2):
                r = await client.post(
                    _DEEPSEEK_SEARCH_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=float(context.config.timeout),
                )
                if not _deepseek_is_retryable(r.status_code):
                    break
                if attempt == 0:
                    logger.warning(
                        "DeepSeek search transient HTTP {}; retrying once in {:.1f}s",
                        r.status_code,
                        _DEEPSEEK_RETRY_DELAY_S,
                    )
                    await asyncio.sleep(_DEEPSEEK_RETRY_DELAY_S)
            assert r is not None
            if r.status_code == 401:
                return ToolResult.error(
                    "Error: DeepSeek search rejected the API key (HTTP 401). "
                    "Set a valid key in tools.web.search.apiKey."
                )
            if r.status_code == 402:
                return ToolResult.error(
                    "Error: DeepSeek account has insufficient balance (HTTP 402). "
                    "Top up at https://platform.deepseek.com/top_up and retry."
                )
            if r.status_code == 429:
                return ToolResult.error(
                    "Error: DeepSeek search rate limited after retry. The account "
                    "limit is 5 QPS; retry later or reduce the frequency of concurrent web_search calls."
                )
            if _deepseek_is_retryable(r.status_code):
                return ToolResult.error(
                    f"Error: DeepSeek search failed ({r.status_code}) after retry. Retry later."
                )
            if not r.is_success:
                # Matches raise_for_status() semantics used by the other
                # providers: non-2xx, including 3xx, is a failure.
                detail = _deepseek_error_detail(r)
                suffix = f": {detail}" if detail else ""
                return ToolResult.error(f"Error: DeepSeek search failed ({r.status_code}){suffix}")
        try:
            data: object = r.json()
        except ValueError:
            return ToolResult.error(
                "Error: DeepSeek search returned a response that was not valid JSON."
            )
        if not isinstance(data, dict):
            return ToolResult.error("Error: DeepSeek search returned an unexpected response shape.")
        raw_results: object = cast(dict[str, Any], data).get("results")
        if raw_results is None:
            raw_results = []
        if not isinstance(raw_results, list):
            return ToolResult.error("Error: DeepSeek search returned an unexpected response shape.")
        results = cast(list[object], raw_results)
        items: list[dict[str, Any]] = []
        for result_value in results:
            if not isinstance(result_value, dict):
                continue
            result = cast(dict[str, Any], result_value)
            # Prefer the long summary written for models; snippet is a
            # frontend-oriented short abstract. Both are stripped, so a
            # whitespace-only summary falls through to the snippet.
            content = _deepseek_text(result.get("summary")) or _deepseek_text(result.get("snippet"))
            content = content[:_DEEPSEEK_MAX_SUMMARY_CHARS]
            date = result.get("date")
            if isinstance(date, str) and date:
                # Same shape as the Volcengine meta line: metadata then body.
                content = f"{date}\n{content}" if content else date
            items.append(
                {
                    "title": _deepseek_text(result.get("title")),
                    "url": _deepseek_text(result.get("url")),
                    "content": content,
                }
            )
        return _format_results(normalized_query, items, n)
    except httpx.TimeoutException:
        return ToolResult.error(
            "Error: DeepSeek search timed out. Retry later or raise tools.web.search.timeout."
        )
    except Exception as e:
        logger.warning(
            "DeepSeek search failed: {}",
            e if tool_log_content_allowed() else type(e).__name__,
        )
        return ToolResult.error(f"Error: DeepSeek search failed: {type(e).__name__}")
