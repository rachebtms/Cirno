"""Stopping a search must not make the synchronous DDGS client overlap its next call."""

import asyncio
from threading import Event

import pytest
from cirno_core.agent.tools.web.search import WebSearchTool
from cirno_core.agent.tools.web_config import WebSearchConfig


@pytest.mark.asyncio
async def test_ddgs_remains_serialized_after_awaiting_call_is_cancelled(monkeypatch):
    first_started = Event()
    second_started = Event()
    release = Event()

    class DDGS:
        def __init__(self, **kwargs):
            pass

        def text(self, query, max_results):
            if query == "first":
                first_started.set()
                assert release.wait(3)
            else:
                second_started.set()
            return [{"title": query, "href": "https://example.com", "body": "result"}]

    monkeypatch.setattr("ddgs.DDGS", DDGS)
    first = asyncio.create_task(WebSearchTool(config=WebSearchConfig(provider="duckduckgo")).execute("first"))
    second = None
    try:
        assert await asyncio.to_thread(first_started.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(WebSearchTool(config=WebSearchConfig(provider="duckduckgo")).execute("second"))
        assert not await asyncio.to_thread(second_started.wait, 0.05)
        release.set()
        assert "Results for: second" in await asyncio.wait_for(second, timeout=2)
        assert second_started.is_set()
    finally:
        release.set()
        for task in (first, second):
            if task is not None and not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
