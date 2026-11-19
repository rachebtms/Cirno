"""Slow URL safety resolution must not freeze the event loop or defeat cancellation."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cirno_core.agent.tools.mcp import connector as mcp_connector
from cirno_core.agent.tools.mcp import http as mcp_http
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.web import network
from cirno_core.agent.tools.web.fetch import WebFetchTool
from cirno_core.config.tools import MCPServerConfig
from cirno_core.security import network as security_network


@pytest.mark.parametrize("boundary", ["fetch_entry", "get_redirect", "stream_redirect", "transport", "mcp_probe", "mcp_hook", "mcp_connector", "extractor"])
async def test_slow_safety_resolution_keeps_loop_responsive_and_cancellable(monkeypatch, boundary):
    started, finished, release = threading.Event(), threading.Event(), threading.Event()

    def slow_validation(*_args, **_kwargs):
        started.set()
        try:
            release.wait(1)
            if boundary == "transport":
                return True, "", ("93.184.216.34",)
            if boundary == "extractor":
                return "Parsed fixture"
            return (False, "Blocked fixture", ()) if boundary == "mcp_probe" else (False, "Blocked fixture")
        finally:
            finished.set()

    stream = None
    inner = None
    if boundary == "extractor":
        tool = WebFetchTool()
        monkeypatch.setattr(tool, "_extract_readable_html", slow_validation)
        response = httpx.Response(200, text="<section>Fixture</section>",
                                  headers={"content-type": "text/html"},
                                  request=httpx.Request("GET", "https://example.test/"))
        monkeypatch.setattr(network, "_get_with_safe_redirects", AsyncMock(return_value=(response, None)))
        monkeypatch.setattr(network, "_fetch_client_kwargs", lambda *_args: {
            "transport": httpx.MockTransport(lambda _request: pytest.fail("Unexpected request")),
        })
        operation = tool._fetch_readability("https://example.test/", "markdown", 100)
    elif boundary == "mcp_connector":
        monkeypatch.setattr(mcp_connector, "validate_url_target", slow_validation)
        operation = mcp_connector.connect_mcp_servers({
            "fixture": MCPServerConfig(type="streamableHttp", url="https://example.test/mcp"),
        }, ToolRegistry())
    elif boundary == "mcp_probe":
        monkeypatch.setattr(mcp_http, "resolve_url_target", slow_validation)
        operation = mcp_http._probe_http_url("https://example.test/")
    elif boundary == "mcp_hook":
        monkeypatch.setattr(mcp_http, "validate_url_target", slow_validation)
        operation = mcp_http._validate_mcp_request_url(httpx.Request("GET", "https://example.test/"))
    elif boundary == "transport":
        monkeypatch.setattr(security_network, "resolve_url_target", slow_validation)
        inner = AsyncMock(spec=httpx.AsyncBaseTransport)
        request = httpx.Request("GET", "https://example.test/")
        operation = security_network.PinnedDNSAsyncTransport(inner=inner).handle_async_request(request)
    else:
        monkeypatch.setattr(network, "_validate_url_safe", slow_validation)
        if boundary == "fetch_entry":
            operation = WebFetchTool().execute("https://example.test/")
        else:
            monkeypatch.setattr(network, "_resolve_url_safe", lambda _url: (True, "", ("93.184.216.34",)))
            response = httpx.Response(302, headers={"location": "https://next.test/"},
                                      request=httpx.Request("GET", "https://example.test/"))
            client = MagicMock()
            client.get = AsyncMock(return_value=response)
            if boundary == "get_redirect":
                operation = network._get_with_safe_redirects(client, "https://example.test/")
            else:
                stream = MagicMock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock())
                client.stream.return_value = stream
                operation = network._stream_with_safe_redirects(client, "https://example.test/")
    task = asyncio.create_task(operation)
    try:
        assert await asyncio.to_thread(started.wait, 2), "Fixture did not enter safety resolution"
        assert not finished.is_set(), "URL resolution blocked the event loop until it finished"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
        if stream is not None:
            stream.__aexit__.assert_awaited_once()
        if inner is not None:
            inner.handle_async_request.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(finished.wait, 2)
