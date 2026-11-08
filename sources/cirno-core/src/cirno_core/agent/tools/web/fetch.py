"""Web fetch."""

from __future__ import annotations

import json
import os
import re
from typing import Any, cast

import httpx
from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.schema import (
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.agent.tools.web import network
from cirno_core.agent.tools.web.constants import _DEFAULT_USER_AGENT, _UNTRUSTED_BANNER
from cirno_core.agent.tools.web.content import _normalize, _strip_tags
from cirno_core.agent.tools.web.safety import _redact_url_for_log, _url_carries_credentials
from cirno_core.agent.tools.web_config import (
    WebFetchConfig,
    WebToolsConfig,
)
from cirno_core.utils.model_messages import build_image_content_blocks
from loguru import logger


@tool_parameters(
    tool_parameters_schema(
        url=StringSchema("URL to fetch"),
        extractMode={
            "type": "string",
            "enum": ["markdown", "text"],
            "default": "markdown",
        },
        maxChars=IntegerSchema(
            description="Maximum output characters; defaults to 50000.", minimum=100
        ),
        required=["url"],
    )
)
class WebFetchTool(Tool):
    """Fetch and extract content from a URL."""

    _scopes = {"core", "subagent"}

    name = "web_fetch"  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
    description = (  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
        "Fetch a URL as readable markdown/text. May fail on login-walled or JavaScript-heavy pages."
    )

    config_key = "web"

    @classmethod
    def config_cls(cls) -> type[WebToolsConfig]:
        return WebToolsConfig

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.config.web.enable

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        return cls(
            config=ctx.config.web.fetch,
            proxy=ctx.network.resolve_proxy(ctx.config.web.use_proxy),
            user_agent=ctx.config.web.user_agent,
        )

    def __init__(
        self,
        config: WebFetchConfig | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
        max_chars: int = 50000,
    ):
        self.config = config if config is not None else WebFetchConfig()
        self.proxy = proxy
        self.user_agent = user_agent or _DEFAULT_USER_AGENT
        self.max_chars = max_chars

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        url: str,
        extract_mode: str = "markdown",
        max_chars: int | None = None,
        **kwargs: Any,
    ) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        url = url.strip(" \t\r\n`\"'")
        extract_mode = kwargs.pop("extractMode", extract_mode)
        max_chars = cast(int, kwargs.pop("maxChars", max_chars) or self.max_chars)
        is_valid, error_msg = network._validate_url_safe(url)
        if not is_valid:
            return ToolResult.error(
                json.dumps(
                    {"error": f"URL validation failed: {error_msg}", "url": url}, ensure_ascii=False
                )
            )

        # Detect and fetch images directly to avoid Jina's textual image captioning.
        # This local preflight also proves that no credential-bearing URL occurs
        # in the redirect chain before the original URL may be sent to Jina.
        jina_remote_safe = False
        try:
            async with httpx.AsyncClient(
                **network._fetch_client_kwargs(self.proxy, 15.0),
            ) as client:
                (
                    r,
                    stream,
                    redirect_error,
                    chain_carries_credentials,
                ) = await network._stream_with_safe_redirects(
                    client,
                    url,
                    headers={"User-Agent": self.user_agent},
                )
                if redirect_error:
                    return ToolResult.error(
                        json.dumps({"error": redirect_error, "url": url}, ensure_ascii=False)
                    )
                if r is None:
                    return ToolResult.error(
                        json.dumps({"error": "Fetch failed", "url": url}, ensure_ascii=False)
                    )
                jina_remote_safe = not chain_carries_credentials

                try:
                    ctype = r.headers.get("content-type", "")
                    # Media types are case-insensitive; parameter values retain their case.
                    media_type, separator, parameters = ctype.partition(";")
                    image_ctype = media_type.strip().lower() + separator + parameters
                    if image_ctype.startswith("image/"):
                        r.raise_for_status()
                        raw = await r.aread()
                        return build_image_content_blocks(
                            raw, image_ctype, url, f"(Image fetched from: {url})"
                        )
                finally:
                    if stream is not None:
                        await stream.__aexit__(None, None, None)
        except Exception as e:
            unsafe_error = network._unsafe_url_request_error(e)
            if unsafe_error is not None:
                return ToolResult.error(
                    json.dumps(
                        {"error": f"URL validation failed: {unsafe_error}", "url": url},
                        ensure_ascii=False,
                    )
                )
            logger.debug(
                "Pre-fetch image detection failed for {} ({})",
                _redact_url_for_log(url),
                type(e).__name__,
            )

        result = None
        if self.config.use_jina_reader and jina_remote_safe:
            result = await self._fetch_jina(url, max_chars)
        if result is None:
            result = await self._fetch_readability(url, extract_mode, max_chars)
        return result

    async def _fetch_jina(self, url: str, max_chars: int) -> str | None:
        """Try fetching via Jina Reader API. Returns None on failure."""
        if _url_carries_credentials(url):
            logger.debug(
                "Skipping Jina Reader for {}: URL carries credential material",
                _redact_url_for_log(url),
            )
            return None
        # httpx already drops the fragment when building the request; strip it
        # explicitly so client-side-only data (OAuth implicit flows put tokens
        # there) stays out of this path even if the transport changes.
        forwarded_url = url.split("#", 1)[0]
        try:
            headers = {"Accept": "application/json", "User-Agent": self.user_agent}
            jina_key = os.environ.get("JINA_API_KEY", "")
            if jina_key:
                headers["Authorization"] = f"Bearer {jina_key}"
            async with httpx.AsyncClient(proxy=self.proxy, timeout=20.0) as client:
                r = await client.get(f"https://r.jina.ai/{forwarded_url}", headers=headers)
                if r.status_code == 429:
                    logger.debug("Jina Reader rate limited, falling back to readability")
                    return None
                r.raise_for_status()

            data = r.json().get("data", {})
            title = data.get("title", "")
            text = data.get("content", "")
            if not text:
                return None

            if title:
                text = f"# {title}\n\n{text}"
            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            text = f"{_UNTRUSTED_BANNER}\n\n{text}"

            return json.dumps(
                {
                    "url": url,
                    "finalUrl": data.get("url", url),
                    "status": r.status_code,
                    "extractor": "jina",
                    "truncated": truncated,
                    "length": len(text),
                    "untrusted": True,
                    "text": text,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            logger.debug(
                "Jina Reader failed for {}, falling back to readability ({})",
                _redact_url_for_log(url),
                type(e).__name__,
            )
            return None

    async def _fetch_readability(self, url: str, extract_mode: str, max_chars: int) -> Any:
        """Local fallback using readability-lxml."""
        try:
            async with httpx.AsyncClient(
                **network._fetch_client_kwargs(self.proxy, 30.0),
            ) as client:
                r, redirect_error = await network._get_with_safe_redirects(
                    client,
                    url,
                    headers={"User-Agent": self.user_agent},
                )
                if redirect_error:
                    return ToolResult.error(
                        json.dumps({"error": redirect_error, "url": url}, ensure_ascii=False)
                    )
                if r is None:
                    return ToolResult.error(
                        json.dumps({"error": "Fetch failed", "url": url}, ensure_ascii=False)
                    )
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")
            # Media types are case-insensitive; parameter values retain their case.
            media_type, separator, parameters = ctype.partition(";")
            image_ctype = media_type.strip().lower() + separator + parameters
            if image_ctype.startswith("image/"):
                return build_image_content_blocks(
                    r.content, image_ctype, url, f"(Image fetched from: {url})"
                )

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                try:
                    text = self._extract_readable_html(r.text, extract_mode)
                    extractor = "readability"
                except Exception as e:
                    logger.warning(
                        "Readability failed for {}, using raw HTML fallback ({})",
                        _redact_url_for_log(url),
                        type(e).__name__,
                    )
                    text, extractor = _normalize(_strip_tags(r.text)), "html"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]
            text = f"{_UNTRUSTED_BANNER}\n\n{text}"

            return json.dumps(
                {
                    "url": url,
                    "finalUrl": str(r.url),
                    "status": r.status_code,
                    "extractor": extractor,
                    "truncated": truncated,
                    "length": len(text),
                    "untrusted": True,
                    "text": text,
                },
                ensure_ascii=False,
            )
        except httpx.ProxyError as e:
            logger.warning(
                "WebFetch proxy error for {} ({})",
                _redact_url_for_log(url),
                type(e).__name__,
            )
            return ToolResult.error(
                json.dumps({"error": f"Proxy error: {e}", "url": url}, ensure_ascii=False)
            )
        except Exception as e:
            logger.warning(
                "WebFetch error for {} ({})",
                _redact_url_for_log(url),
                type(e).__name__,
            )
            return ToolResult.error(json.dumps({"error": str(e), "url": url}, ensure_ascii=False))

    def _extract_readable_html(self, html_content: str, extract_mode: str) -> str:
        from readability import Document  # pyright: ignore[reportMissingTypeStubs]

        doc = Document(html_content)
        summary = cast(str, doc.summary())
        content = self._to_markdown(summary) if extract_mode == "markdown" else _strip_tags(summary)
        return f"# {doc.title()}\n\n{content}" if doc.title() else content

    def _to_markdown(self, html_content: str) -> str:
        """Convert HTML to markdown."""
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
            html_content,
            flags=re.I,
        )
        text = re.sub(
            r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
            lambda m: f"\n{'#' * int(m[1])} {_strip_tags(m[2])}\n",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"<li[^>]*>([\s\S]*?)</li>", lambda m: f"\n- {_strip_tags(m[1])}", text, flags=re.I
        )
        text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
        text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
        return _normalize(_strip_tags(text))
