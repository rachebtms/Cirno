"""Web capabilities exposed to the built-in tool loader."""

from cirno_core.agent.tools.web.fetch import WebFetchTool
from cirno_core.agent.tools.web.search import WebSearchTool

__all__ = ["WebFetchTool", "WebSearchTool"]
