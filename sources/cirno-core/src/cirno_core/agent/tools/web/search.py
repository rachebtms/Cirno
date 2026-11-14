"""Web search."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.context import ToolContext, tool_log_content_allowed
from cirno_core.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.agent.tools.web.constants import _DEFAULT_USER_AGENT
from cirno_core.agent.tools.web.context import SearchContext
from cirno_core.agent.tools.web.searches import (
    anysearch,
    bocha,
    brave,
    deepseek,
    duckduckgo,
    exa,
    jina,
    kagi,
    keenable,
    olostep,
    searxng,
    serper,
    tavily,
    volcengine,
)
from cirno_core.agent.tools.web_config import (
    WebSearchConfig,
    WebToolsConfig,
)
from loguru import logger


@tool_parameters(
    tool_parameters_schema(
        query=StringSchema("Search query"),
        count=IntegerSchema(
            description="Maximum results; uses the configured default if omitted.",
            minimum=1,
            maximum=10,
        ),
        timeRange=StringSchema(
            "Optional time filter for providers that support it: "
            "OneDay, OneWeek, OneMonth, OneYear, or YYYY-MM-DD..YYYY-MM-DD",
        ),
        authLevel=IntegerSchema(
            description="Optional authority filter for providers that support it: 0=all, 1=authoritative",
            minimum=0,
            maximum=1,
        ),
        queryRewrite=BooleanSchema(
            description="Optional provider-side query rewrite for conversational or ambiguous searches",
        ),
        required=["query"],
    )
)
class WebSearchTool(Tool):
    """Search the web using configured provider."""

    _scopes = {"core", "subagent"}

    name = "web_search"  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
    description = (  # pyright: ignore[reportIncompatibleMethodOverride, reportAssignmentType]
        "Search the web for titles, URLs, and snippets. Use web_fetch to read a specific page."
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
        config_loader: Callable[[], WebSearchConfig] | None = None
        if ctx.provider_snapshot_loader is not None:

            def _load_search_config() -> WebSearchConfig:
                from cirno_core.config.loader import load_config, resolve_config_env_vars

                return resolve_config_env_vars(load_config()).tools.web.search

            config_loader = _load_search_config
        return cls(
            config=ctx.config.web.search,
            proxy=ctx.network.resolve_proxy(ctx.config.web.use_proxy),
            user_agent=ctx.config.web.user_agent,
            config_loader=config_loader,
        )

    def __init__(
        self,
        config: WebSearchConfig | None = None,
        proxy: str | None = None,
        user_agent: str | None = None,
        config_loader: Callable[[], WebSearchConfig] | None = None,
    ):
        self.config = config if config is not None else WebSearchConfig()
        self.proxy = proxy
        self.user_agent = user_agent if user_agent is not None else _DEFAULT_USER_AGENT
        self._config_loader = config_loader

    def _refresh_config(self) -> None:
        if self._config_loader is None:
            return
        self.config = self._config_loader()

    def _effective_provider(self) -> str:
        """Resolve the backend that execute() will actually use."""
        self._refresh_config()
        provider = self.config.provider.strip().lower() or "duckduckgo"
        if provider == "duckduckgo":
            return "duckduckgo"
        if provider == "brave":
            api_key = self.config.api_key or os.environ.get("BRAVE_API_KEY", "")
            return "brave" if api_key else "duckduckgo"
        if provider == "tavily":
            api_key = self.config.api_key or os.environ.get("TAVILY_API_KEY", "")
            return "tavily" if api_key else "duckduckgo"
        if provider == "searxng":
            base_url = (self.config.base_url or os.environ.get("SEARXNG_BASE_URL", "")).strip()
            return "searxng" if base_url else "duckduckgo"
        if provider == "jina":
            api_key = self.config.api_key or os.environ.get("JINA_API_KEY", "")
            return "jina" if api_key else "duckduckgo"
        if provider == "kagi":
            api_key = self.config.api_key or os.environ.get("KAGI_API_KEY", "")
            return "kagi" if api_key else "duckduckgo"
        if provider == "exa":
            api_key = self.config.api_key or os.environ.get("EXA_API_KEY", "")
            return "exa" if api_key else "duckduckgo"
        if provider == "olostep":
            api_key = self.config.api_key or os.environ.get("OLOSTEP_API_KEY", "")
            return "olostep" if api_key else "duckduckgo"
        if provider == "bocha":
            api_key = self.config.api_key or os.environ.get("BOCHA_API_KEY", "")
            return "bocha" if api_key else "duckduckgo"
        if provider == "volcengine":
            api_key = (
                self.config.api_key
                or os.environ.get("VOLCENGINE_SEARCH_API_KEY", "")
                or os.environ.get("WEB_SEARCH_API_KEY", "")
            )
            return "volcengine" if api_key else "duckduckgo"
        if provider == "keenable":
            return "keenable"
        if provider == "anysearch":
            return "anysearch"
        if provider == "serper":
            api_key = self.config.api_key or os.environ.get("SERPER_API_KEY", "")
            return "serper" if api_key else "duckduckgo"
        return provider

    @property
    def read_only(self) -> bool:
        return True

    @property
    def exclusive(self) -> bool:
        """DuckDuckGo searches are serialized because ddgs is not concurrency-safe."""
        try:
            return self._effective_provider() == "duckduckgo"
        except Exception:
            # Admission is conservative; execute reports the configuration error
            # instead of letting batch partitioning abort unrelated tools.
            return True

    async def execute(
        self,
        query: str,
        count: int | None = None,
        time_range: str | None = None,
        auth_level: int | None = None,
        query_rewrite: bool | None = None,
        **kwargs: Any,
    ) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
        try:
            self._refresh_config()
        except Exception as error:
            logger.opt(exception=tool_log_content_allowed()).error("Failed to refresh web search config")
            return ToolResult.error(f"Cannot load current web search configuration ({type(error).__name__}); check Settings and server diagnostics. No search was sent.")
        context = SearchContext(self.config.model_copy(deep=True), self.proxy, self.user_agent)
        provider = context.config.provider.strip().lower() or "duckduckgo"
        n = min(max(count or self.config.max_results, 1), 10)

        if provider == "olostep":
            return await olostep.search(context, query, n)
        if provider == "volcengine":
            return await volcengine.search(
                context,
                query,
                n,
                time_range=kwargs.get("timeRange", kwargs.get("time_range", time_range)),
                auth_level=kwargs.get("authLevel", kwargs.get("auth_level", auth_level)),
                query_rewrite=kwargs.get(
                    "queryRewrite", kwargs.get("query_rewrite", query_rewrite)
                ),
            )
        if provider == "duckduckgo":
            return await duckduckgo.search(context, query, n)
        elif provider == "tavily":
            return await tavily.search(context, query, n)
        elif provider == "searxng":
            return await searxng.search(context, query, n)
        elif provider == "jina":
            return await jina.search(context, query, n)
        elif provider == "brave":
            return await brave.search(context, query, n)
        elif provider == "kagi":
            return await kagi.search(context, query, n)
        elif provider == "exa":
            return await exa.search(context, query, n)
        elif provider == "bocha":
            return await bocha.search(
                context,
                query,
                n,
                freshness=kwargs.get("freshness", "noLimit"),
            )
        elif provider == "keenable":
            return await keenable.search(context, query, n)
        elif provider == "anysearch":
            return await anysearch.search(context, query, n)
        elif provider == "deepseek":
            return await deepseek.search(context, query, n)
        elif provider == "serper":
            return await serper.search(context, query, n)
        else:
            return ToolResult.error(f"Error: unknown search provider '{provider}'")
