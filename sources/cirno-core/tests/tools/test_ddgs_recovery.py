"""Serial recovery keeps the original search deadline and cancellation boundary."""

import asyncio
import time
from threading import Event

import pytest
from ddgs.exceptions import DDGSException

from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.web.search import WebSearchTool
from cirno_core.agent.tools.web_config import WebSearchConfig


def install_ddgs(monkeypatch, responses):
    calls, timeouts = [], []

    class DDGS:
        def __init__(self, *, timeout, proxy):
            timeouts.append(timeout)

        def text(self, query, max_results):
            calls.append(query)
            response = responses[len(calls) - 1]
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr("ddgs.DDGS", DDGS)
    return calls, timeouts


async def test_transient_engine_failure_recovers_in_one_tool_call(monkeypatch):
    calls, timeouts = install_ddgs(monkeypatch, [DDGSException("temporary upstream failure"), [{"title": "Found", "href": "https://example.com", "body": "verified"}]])
    tool = WebSearchTool(config=WebSearchConfig(timeout=30))
    result = await tool.execute("paper title")
    assert "Found" in result and not is_tool_error_result(result)
    assert calls == ["paper title", "paper title"] and timeouts == [10, 10]


async def test_retry_does_not_extend_the_original_deadline_or_hide_library_error(monkeypatch):
    calls, timeouts = install_ddgs(monkeypatch, [DDGSException("engine TLS handshake failed")])
    tool = WebSearchTool(config=WebSearchConfig())
    tool.config.timeout = .1
    started = time.monotonic()
    result = await tool.execute("paper title")
    assert time.monotonic() - started < .5
    assert len(calls) == 1 and 0 < timeouts[0] <= .1
    assert is_tool_error_result(result) and "engine TLS handshake failed" in result


async def test_error_details_do_not_leak_proxy_or_api_credentials(monkeypatch):
    secret = "proxy-password"
    proxy = f"http://owner:{secret}@localhost:1234"
    install_ddgs(monkeypatch, [DDGSException(f"Cannot connect to {proxy}: {secret}; key=private-api-key")])
    tool = WebSearchTool(config=WebSearchConfig(api_key="private-api-key"), proxy=proxy)
    tool.config.timeout = .1
    result = await tool.execute("paper title")
    assert secret not in result and "private-api-key" not in result
    assert "DDGSException" in result and "[redacted]" in result


async def test_cancellation_during_retry_backoff_never_starts_another_search(monkeypatch):
    attempted = Event()
    calls = []

    class DDGS:
        def __init__(self, **kwargs):
            pass

        def text(self, query, max_results):
            calls.append(query)
            attempted.set()
            raise DDGSException("temporarily unavailable")

    monkeypatch.setattr("ddgs.DDGS", DDGS)
    task = asyncio.create_task(WebSearchTool(config=WebSearchConfig()).execute("paper title"))
    assert await asyncio.to_thread(attempted.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # A subsequent search also proves the cancelled thread released the shared lock.
    install_ddgs(monkeypatch, [[{"title": "Next", "href": "https://example.com", "body": "verified"}]])
    result = await asyncio.wait_for(WebSearchTool(config=WebSearchConfig()).execute("next query"), 1)
    assert "Next" in result and calls == ["paper title"]
