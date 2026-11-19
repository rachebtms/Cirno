"""Fetch limits apply before materializing responses and across all extractors."""

import gzip
import json

import httpx
import pytest
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.web import network
from cirno_core.agent.tools.web.fetch import WebFetchTool
from cirno_core.agent.tools.web_config import WebFetchConfig


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("extractor", ["image", "local", "jina"])
async def test_oversized_fetch_is_an_error_without_body_read_or_retry(monkeypatch, extractor):
    requests, streams = [], []

    def handle(request):
        requests.append(str(request.url))
        stream = Stream([b'{}'])
        streams.append(stream)
        mime = "image/png" if extractor == "image" else "text/html"
        if request.url.host == "r.jina.ai":
            mime = "application/json"
        return httpx.Response(200, headers={"Content-Type": mime, "Content-Length": str(1024 * 1024 + 1)},
                              stream=stream, request=request)

    client_type = httpx.AsyncClient
    class Client(client_type):
        def __init__(self, **kwargs):
            kwargs.pop("proxy", None)
            kwargs["transport"] = httpx.MockTransport(handle)
            kwargs["trust_env"] = False
            super().__init__(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(network, "_pinned_dns_transport", lambda: httpx.MockTransport(handle))
    monkeypatch.setattr(network, "_validate_url_safe", lambda _url: (True, ""))
    monkeypatch.setattr(network, "_resolve_url_safe", lambda _url: (True, "", ("93.184.216.34",)))
    tool = WebFetchTool(WebFetchConfig(use_jina_reader=extractor == "jina", max_response_mb=1))
    result = await tool.execute("https://example.test/page", maxChars=100)
    assert is_tool_error_result(result)
    assert "1,048,576-byte limit" in json.loads(result)["error"]
    assert len(requests) == (1 if extractor == "image" else 2)
    assert all(stream.closed and stream.reads == 0 for stream in streams)


@pytest.mark.parametrize("kind", ["chunked", "compressed", "allowed_compressed"])
async def test_bounded_redirect_fetch_counts_decoded_bytes_and_closes_stream(monkeypatch, kind):
    allowed = kind == "allowed_compressed"
    body = b"valid response" if allowed else b"x" * 100
    headers = {} if kind == "chunked" else {"content-encoding": "gzip"}
    chunks = [b"x" * 16] * 8 if kind == "chunked" else [gzip.compress(body)]
    stream = Stream(chunks)
    def handle(request):
        return httpx.Response(200, headers=headers, stream=stream, request=request)
    monkeypatch.setattr(network, "_resolve_url_safe", lambda _url: (True, "", ("93.184.216.34",)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        if allowed:
            response, error = await network._get_with_safe_redirects(client, "https://example.test/", max_response_bytes=64)
            assert error is None
            assert response.content == body
            assert response.text == "valid response"
        else:
            with pytest.raises(network.ResponseTooLargeError):
                await network._get_with_safe_redirects(client, "https://example.test/", max_response_bytes=32)
    assert stream.closed
    if kind == "chunked":
        assert stream.reads < len(chunks)
