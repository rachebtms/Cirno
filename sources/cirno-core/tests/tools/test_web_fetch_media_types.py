"""Response media types are case insensitive for every extraction branch."""

import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from cirno_core.agent.tools.web import network
from cirno_core.agent.tools.web.fetch import WebFetchTool


@pytest.mark.parametrize("media_type,body,extractor", [
    ("Application/JSON; charset=UTF-8", '{"key":"value"}', "json"),
    ("Text/Html; charset=UTF-8", "<section>Readable content</section>", "readability"),
])
async def test_case_insensitive_media_type_selects_correct_extractor(monkeypatch, media_type, body, extractor):
    response = httpx.Response(
        200, headers={"content-type": media_type}, text=body,
        request=httpx.Request("GET", "https://example.test/page"),
    )
    fetch = AsyncMock(return_value=(response, None))
    monkeypatch.setattr(network, "_get_with_safe_redirects", fetch)
    # No DNS lookup or socket is possible in this test.
    monkeypatch.setattr(network, "_fetch_client_kwargs", lambda *_args: {
        "transport": httpx.MockTransport(lambda _request: pytest.fail("Unexpected HTTP request")),
    })
    tool = WebFetchTool()
    readable = Mock(return_value="Readable content")
    monkeypatch.setattr(tool, "_extract_readable_html", readable)
    result = json.loads(await tool._fetch_readability("https://example.test/page", "text", 1000))
    assert result["extractor"] == extractor
    assert result["untrusted"] is True
    if extractor == "json":
        assert json.dumps({"key": "value"}, indent=2) in result["text"]
        readable.assert_not_called()
    else:
        readable.assert_called_once_with(body, "text")
