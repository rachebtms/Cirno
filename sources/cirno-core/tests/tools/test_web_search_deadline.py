"""Search settings govern adapter requests and the complete serial search."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.web import searches
from cirno_core.agent.tools.web.search import WebSearchTool
from cirno_core.agent.tools.web_config import WebSearchConfig


@pytest.mark.parametrize("provider", ["brave", "tavily", "jina", "kagi", "searxng"])
async def test_adapter_request_uses_saved_search_timeout(monkeypatch, provider):
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": {"search": []}} if provider == "kagi" else {"data": []}
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=client))
    tool = WebSearchTool(config=WebSearchConfig(
        provider=provider, api_key="fixture", base_url="https://search.example.test", timeout=73,
    ))
    result = await tool.execute("query")
    assert not is_tool_error_result(result)
    request = client.get if client.get.await_count else client.post
    request.assert_awaited_once()
    assert request.call_args.kwargs["timeout"] == 73


@pytest.mark.parametrize("provider", ["brave", "olostep", "jina", "duckduckgo"])
async def test_search_deadline_cancels_adapter_without_another_request(monkeypatch, provider):
    stopped = asyncio.Event()

    async def search(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    adapter = __import__(searches.__name__ + "." + provider, fromlist=["search"])
    call = AsyncMock(side_effect=search)
    monkeypatch.setattr(adapter, "search", call)
    tool = WebSearchTool(config=WebSearchConfig(provider=provider))
    tool.config.timeout = .02
    result = await asyncio.wait_for(tool.execute("query"), .3)
    assert is_tool_error_result(result)
    assert "timed out" in result and "tool deadline" in result
    assert stopped.is_set()
    call.assert_awaited_once()


async def test_external_cancellation_remains_cancellation(monkeypatch):
    entered = asyncio.Event()

    async def search(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", search)
    task = asyncio.create_task(WebSearchTool(config=WebSearchConfig(provider="brave")).execute("query"))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_rate_limit_backoff_cannot_extend_the_search_deadline(monkeypatch):
    response = MagicMock(status_code=429)
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("httpx.AsyncClient", MagicMock(return_value=client))
    tool = WebSearchTool(config=WebSearchConfig(provider="brave", api_key="fixture"))
    tool.config.timeout = .02
    result = await asyncio.wait_for(tool.execute("query"), .3)
    assert is_tool_error_result(result) and "tool deadline" in result
    client.get.assert_awaited_once()
