"""Inspect HTTP connection arguments using fake SDK contexts and fake clients."""

import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from cirno_core.agent.tools.mcp import connector
from cirno_core.agent.tools.mcp.connections import close_mcp_connections
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.tools import MCPServerConfig


@pytest.mark.parametrize("kind", ["sse", "sse-override", "streamableHttp"])
async def test_http_headers_replace_case_variants_instead_of_sending_duplicates(monkeypatch, kind):
    observed = []

    class Client:
        def __init__(self, **kwargs):
            observed.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    @asynccontextmanager
    async def sse(_url, *, httpx_client_factory):
        headers = {"AUTHORIZATION": "Bearer sdk-secret", "ACCEPT": "sdk-accept"} if kind == "sse-override" else None
        async with httpx_client_factory(headers=headers):
            yield object(), object()

    @asynccontextmanager
    async def streamable(_url, *, http_client):
        assert isinstance(http_client, Client)
        yield object(), object(), object()

    @asynccontextmanager
    async def session(read, write):
        yield SimpleNamespace(initialize=AsyncMock(return_value=SimpleNamespace(capabilities=object())))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("No native programs or real SDK contexts allowed")

    for name, attributes in {
        "mcp": {"ClientSession": session, "StdioServerParameters": forbidden},
        "mcp.client": {},
        "mcp.client.stdio": {"stdio_client": forbidden},
        "mcp.client.sse": {"sse_client": sse},
        "mcp.client.streamable_http": {"streamable_http_client": streamable},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(connector.httpx, "AsyncClient", Client)
    monkeypatch.setattr(connector, "validate_url_target", lambda _url: (True, ""))
    monkeypatch.setattr(connector, "_probe_http_url", AsyncMock(return_value=True))
    monkeypatch.setattr(connector, "_pinned_transport_kwargs", lambda _proxy: {})
    monkeypatch.setattr(connector, "register_capabilities", AsyncMock(return_value=0))
    monkeypatch.setattr(connector, "_filter_malformed_mcp_progress_notifications", lambda read, _name: read)
    cfg = MCPServerConfig(
        type="sse" if kind.startswith("sse") else "streamableHttp",
        url="https://fixture.invalid/mcp",
        headers={"Authorization": "Bearer obsolete", "authorization": "Bearer configured-secret", "accept": "configured-accept", "X-Trace": "keep"},
    )
    connections = await connector.connect_mcp_servers({"fixture": cfg}, ToolRegistry())
    try:
        assert set(connections) == {"fixture"}
        assert len(observed) == 1
        headers = httpx.Headers(observed[0]["headers"])
        expected = "Bearer sdk-secret" if kind == "sse-override" else "Bearer configured-secret"
        assert headers.get_list("authorization") == [expected]
        assert headers.get_list("accept") == ["sdk-accept" if kind == "sse-override" else "configured-accept"]
        assert headers["x-trace"] == "keep"
    finally:
        assert await close_mcp_connections(connections) == {}
