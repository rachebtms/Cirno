"""Request-scoped search configuration shared by provider adapters."""

from dataclasses import dataclass

from cirno_core.agent.tools.web_config import WebSearchConfig


@dataclass(frozen=True, slots=True)
class SearchContext:
    config: WebSearchConfig
    proxy: str | None
    user_agent: str
