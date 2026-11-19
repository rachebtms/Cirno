"""Local authorization loss retires live MCP capabilities without reconnecting."""

import asyncio
from types import SimpleNamespace

import pytest
from cirno_core.agent.tools.mcp.connections import OwnedMCPConnection
from cirno_core.agent.tools.mcp.provider import MCPProvider
from cirno_core.agent.tools.mcp.wrappers import MCPToolWrapper
from cirno_core.agent.tools.mcp_oauth import MCPOAuthStorage, delete_mcp_oauth_credentials
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from mcp import types
from mcp.shared.auth import OAuthToken


@pytest.mark.parametrize("entry", ["connect", "reload", "reconnect", "reconnect-stale-reference"])
async def test_authorization_loss_retires_only_its_live_connection_and_cached_tools(
    tmp_path, monkeypatch, entry
):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers = {
        "revoked": MCPServerConfig(
            type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
        ),
        "healthy": MCPServerConfig(command="fixture"),
    }
    save_config(config, path)
    await MCPOAuthStorage("revoked", "https://fixture.test/mcp", config_path=path).set_tokens(
        OAuthToken(access_token="fixture-token")
    )
    attempted = []
    closed = []

    async def connect(servers, registry, **kwargs):
        attempted.append(set(servers))
        connections = {}
        for name in servers:

            async def close(name=name):
                closed.append(name)

            connections[name] = SimpleNamespace(aclose=close)
            registry.register(
                MCPToolWrapper(
                    SimpleNamespace(),
                    name,
                    types.Tool(name="probe", inputSchema={"type": "object"}),
                )
            )
        return connections

    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", connect)
    registry = ToolRegistry()
    provider = MCPProvider.from_config(load_config(path), registry)
    try:
        await provider.connect()
        old_tool = registry.get("mcp_revoked_probe")
        assert old_tool is not None
        assert "mcp_revoked_probe" in str(registry.get_definitions())
        delete_mcp_oauth_credentials("revoked", config_path=path)
        if entry == "reload":
            receipt = await provider.reload()
        elif entry.startswith("reconnect"):
            stale = old_tool if entry == "reconnect" else SimpleNamespace()
            assert (
                await provider._refresh_terminated_server("revoked", "mcp_revoked_probe", stale)
                is None
            )
        else:
            await provider.connect()
        assert attempted == [{"revoked", "healthy"}], "A revoked connection was reconnected"
        assert provider.connected_server_names == {"healthy"}
        assert not registry.has("mcp_revoked_probe")
        assert "mcp_revoked_probe" not in str(registry.get_definitions())
        assert registry.has("mcp_healthy_probe")
        assert provider.runtime_status() == {"healthy": "connected"}
        assert closed == ["revoked"]
        if entry == "reload":
            assert receipt["tools_removed"] == 1
            assert receipt["authorization_required"] == ["revoked"]
            assert receipt["requires_restart"] is False
        current = MCPOAuthStorage("revoked", "https://fixture.test/mcp", config_path=path)
        await current.set_tokens(OAuthToken(access_token="renewed-fixture-token"))
        await provider.connect()
        assert provider.connected_server_names == {"healthy", "revoked"}
        assert registry.get("mcp_revoked_probe") is not old_tool
        assert registry.has("mcp_revoked_probe")
    finally:
        await provider.aclose()


async def test_cancelled_reload_withdraws_all_old_capabilities_and_keeps_the_desired_config(
    monkeypatch,
):
    cfg = MCPServerConfig(command="fixture")
    desired = {name: cfg for name in ("old1", "old2", "healthy")}
    registry = ToolRegistry()
    close_requested = asyncio.Event()
    close_started = asyncio.Event()
    release = asyncio.Event()
    closed = []
    attempted = []
    owners = []

    async def own_first():
        await close_requested.wait()
        close_started.set()
        await release.wait()
        closed.append("old1")

    async def connect(servers, registry, **kwargs):
        attempted.append(set(servers))
        connections = {}
        for name in servers:
            registry.register(
                MCPToolWrapper(
                    SimpleNamespace(),
                    name,
                    types.Tool(name="probe", inputSchema={"type": "object"}),
                )
            )
            if name == "old1":
                owner = asyncio.create_task(own_first())
                owners.append(owner)
                connections[name] = OwnedMCPConnection(owner, close_requested)
            else:

                async def close(name=name):
                    closed.append(name)

                connections[name] = SimpleNamespace(aclose=close)
        return connections

    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", connect)
    from cirno_core.config.network import NetworkConfig

    provider = MCPProvider(
        desired, registry, server_loader=lambda: (dict(desired), NetworkConfig())
    )
    operation = None
    try:
        await provider.connect()
        del desired["old1"], desired["old2"]
        operation = asyncio.create_task(provider.reload())
        await asyncio.wait_for(close_started.wait(), 1)
        withdrawn = not registry.has("mcp_old1_probe") and not registry.has("mcp_old2_probe")
        configured = provider.configured_server_names
        operation.cancel()
        await asyncio.sleep(0)
        operation.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert withdrawn, "A slow close left other removed capabilities registered"
        assert configured == {"healthy"}, (
            "Reload had not published the desired configuration before cleanup"
        )
        assert closed == ["old1", "old2"]
        await provider.connect()
        assert attempted == [{"old1", "old2", "healthy"}]
        assert provider.connected_server_names == {"healthy"}
    finally:
        release.set()
        close_requested.set()
        if operation is not None:
            await asyncio.gather(operation, return_exceptions=True)
        await provider.aclose()
        await asyncio.gather(*owners, return_exceptions=True)
