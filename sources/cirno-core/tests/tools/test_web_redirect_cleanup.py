"""Malformed upstream redirect locations do not retain an open response."""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from cirno_core.agent.tools.web import network


@pytest.mark.parametrize("streamed", [False, True])
async def test_malformed_redirect_closes_response_and_returns_a_blocked_result(monkeypatch, streamed):
    url = "https://fixture.example.test/page"
    response = httpx.Response(302, headers={"location": "https://[invalid-host/"},
                              request=httpx.Request("GET", url))
    response.aclose = AsyncMock()
    stream = Mock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock())
    client = Mock(get=AsyncMock(return_value=response), stream=Mock(return_value=stream))
    monkeypatch.setattr(network, "_resolve_url_safe", lambda _url: (True, "", ("203.0.113.7",)))
    with_error = None
    try:
        if streamed:
            result, _stream, error, _credentials = await network._stream_with_safe_redirects(client, url)
        else:
            result, error = await network._get_with_safe_redirects(client, url)
    except ValueError as exc:
        with_error = exc
    if streamed:
        stream.__aexit__.assert_awaited_once()
    else:
        response.aclose.assert_awaited_once()
    assert with_error is None
    assert result is None
    assert "Redirect blocked" in error


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("allowed", [False, True])
async def test_redirect_keeps_valid_final_response_owned_and_closes_rejected_hop(monkeypatch, streamed, allowed):
    url = "https://fixture.example.test/page"
    first = httpx.Response(302, headers={"location": "/target?access_token=fixture"}, request=httpx.Request("GET", url))
    final = httpx.Response(200, request=httpx.Request("GET", url + "/target"))
    first.aclose, final.aclose = AsyncMock(), AsyncMock()
    streams = [Mock(__aenter__=AsyncMock(return_value=row), __aexit__=AsyncMock()) for row in (first, final)]
    client = Mock(get=AsyncMock(side_effect=[first, final]), stream=Mock(side_effect=streams))
    monkeypatch.setattr(network, "_resolve_url_safe", lambda _url: (True, "", ("203.0.113.7",)))
    monkeypatch.setattr(network, "_validate_url_safe", lambda _url: (allowed, "Fixture blocked target"))
    if streamed:
        result, stream, error, credentials = await network._stream_with_safe_redirects(client, url)
        streams[0].__aexit__.assert_awaited_once()
        streams[1].__aexit__.assert_not_awaited()
        assert credentials is True
        if allowed:
            assert stream is streams[1]
            await stream.__aexit__(None, None, None)
        else:
            assert client.stream.call_count == 1
    else:
        result, error = await network._get_with_safe_redirects(client, url)
        first.aclose.assert_awaited_once()
        final.aclose.assert_not_awaited()
        if not allowed:
            client.get.assert_awaited_once()
    assert result is (final if allowed else None)
    assert (error is None) if allowed else "Fixture blocked target" in error


async def test_fetch_reports_malformed_redirect_without_trying_another_extractor(monkeypatch):
    import json

    from cirno_core.agent.tools.registry import is_tool_error_result
    from cirno_core.agent.tools.web.fetch import WebFetchTool

    url = "https://fixture.example.test/page"
    response = httpx.Response(302, headers={"location": "https://[invalid-host/"}, request=httpx.Request("GET", url))
    stream = Mock(__aenter__=AsyncMock(return_value=response), __aexit__=AsyncMock())
    client = Mock(__aenter__=AsyncMock(), __aexit__=AsyncMock(), stream=Mock(return_value=stream))
    client.__aenter__.return_value = client
    monkeypatch.setattr("httpx.AsyncClient", Mock(return_value=client))
    monkeypatch.setattr(network, "_fetch_client_kwargs", lambda *_args: {})
    monkeypatch.setattr(network, "_resolve_url_safe", lambda _url: (True, "", ("203.0.113.7",)))
    monkeypatch.setattr(network, "_validate_url_safe", lambda _url: (True, ""))
    fallback = AsyncMock(return_value="Unexpected retry")
    tool = WebFetchTool()
    monkeypatch.setattr(tool, "_fetch_readability", fallback)
    result = await tool.execute(url)
    assert is_tool_error_result(result)
    assert "Redirect blocked" in json.loads(result)["error"]
    stream.__aexit__.assert_awaited_once()
    client.stream.assert_called_once()
    fallback.assert_not_awaited()
