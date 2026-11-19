"""MCP metadata I/O stays off the event loop and accepted reloads retain ownership."""

import asyncio
import hashlib
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.mcp.provider import MCPProvider
from cirno_core.agent.tools.mcp_oauth import (
    mcp_oauth_has_credentials,
    mcp_oauth_stored_server_names,
)
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import MCPServerConfig


@pytest.mark.parametrize("entry", ["connect", "reload", "reconnect"])
async def test_provider_credential_and_loader_io_never_runs_on_event_loop(monkeypatch, entry):
    loop_thread = threading.get_ident()
    seen = []
    cfg = MCPServerConfig(type="streamableHttp", auth="oauth", url="https://fixture.test/mcp")

    def check(name, url):
        assert threading.get_ident() != loop_thread, "Credential file I/O ran on the event loop"
        seen.append("credentials")
        return False

    def load():
        assert threading.get_ident() != loop_thread, "Config/plugin file I/O ran on the event loop"
        seen.append("loader")
        return {"fixture": cfg}, NetworkConfig()

    transport = AsyncMock()
    monkeypatch.setattr("cirno_core.agent.tools.mcp_oauth.mcp_oauth_has_credentials", check)
    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", transport)
    provider = MCPProvider({"fixture": cfg}, ToolRegistry(), server_loader=load)
    try:
        if entry == "connect":
            await provider.connect()
        elif entry == "reload":
            receipt = await provider.reload()
            assert receipt["ok"] is True
            assert receipt["authorization_required"] == ["fixture"]
        else:
            assert (
                await provider._refresh_terminated_server(
                    "fixture", "mcp_fixture_probe", SimpleNamespace()
                )
                is None
            )
        assert seen == (["loader", "credentials"] if entry == "reload" else ["credentials"])
        transport.assert_not_awaited()
    finally:
        await provider.aclose()


@pytest.mark.parametrize("fails", [False, True])
async def test_cancelled_reload_waits_for_accepted_loader_and_commits_no_new_connections(
    tmp_path, monkeypatch, fails
):
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    started = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    cfg = MCPServerConfig(command="fixture")
    marker = tmp_path / "owned-loader.txt"

    def load():
        loop.call_soon_threadsafe(started.set)
        try:
            assert threading.get_ident() != loop_thread, "Loader blocked the event loop"
            assert release.wait(2), "Fixture did not release loader"
            marker.write_text("Accepted plugin materialization finished")
            if fails:
                raise OSError("Fixture loader failed after accepted materialization")
            return {"desired": cfg}, NetworkConfig()
        finally:
            completed.set()

    transport = AsyncMock()
    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", transport)
    registry = ToolRegistry()
    registry.register(SimpleNamespace(name="mcp_old_probe"))
    provider = MCPProvider({"old": cfg}, registry, server_loader=load)
    operation = asyncio.create_task(provider.reload())
    try:
        await asyncio.wait_for(started.wait(), 1)
        operation.cancel()
        await asyncio.sleep(0)
        operation.cancel()
        await asyncio.sleep(0)
        pending = not operation.done()
    finally:
        release.set()
        outcomes = await asyncio.gather(operation, return_exceptions=True)
        assert await asyncio.to_thread(completed.wait, 2)
    try:
        assert pending, "Reload detached its accepted config/plugin loader"
        assert isinstance(outcomes[0], asyncio.CancelledError)
        assert marker.read_text() == "Accepted plugin materialization finished"
        assert provider.configured_server_names == ({"old"} if fails else {"desired"})
        assert registry.has("mcp_old_probe") is fails
        assert provider.connected_server_names == set()
        transport.assert_not_awaited()
    finally:
        await provider.aclose()


def test_credential_presence_probe_is_an_atomic_read_without_token_store_lock_or_write(
    tmp_path, monkeypatch
):
    path = tmp_path / "config.json"
    store = tmp_path / "state" / "auth" / "mcp.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": {
                    "fixture": {
                        "server_fingerprint": hashlib.sha256(
                            b"https://fixture.test/mcp"
                        ).hexdigest(),
                        "tokens": {"access_token": "fixture-token"},
                    }
                },
                "generations": {},
            }
        )
    )
    before = store.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only credential presence probe acquired a writer lock or wrote a lease")

    monkeypatch.setattr("cirno_core.agent.tools.mcp_oauth_storage._with_store_lock", forbidden)
    monkeypatch.setattr("cirno_core.agent.tools.mcp_oauth_storage._write_store_unlocked", forbidden)
    assert mcp_oauth_has_credentials("fixture", "https://fixture.test/mcp", config_path=path)
    assert not mcp_oauth_has_credentials(
        "fixture", "https://other.fixture.test/mcp", config_path=path
    )
    assert not mcp_oauth_has_credentials("other", "https://fixture.test/mcp", config_path=path)
    assert mcp_oauth_stored_server_names(config_path=path) == {"fixture"}
    assert store.read_bytes() == before


def test_default_metadata_probes_do_not_create_an_instance_state_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", tmp_path / "config.json")
    assert mcp_oauth_stored_server_names() == set()
    assert not mcp_oauth_has_credentials("fixture", "https://fixture.test/mcp")
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("entry", ["connect", "reconnect"])
async def test_shutdown_during_credential_io_does_not_start_a_new_connection(monkeypatch, entry):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()

    def check(name, url):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(2), "Fixture did not release credential read"
        return True

    transport = AsyncMock(return_value={})
    monkeypatch.setattr("cirno_core.agent.tools.mcp_oauth.mcp_oauth_has_credentials", check)
    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", transport)
    provider = MCPProvider(
        {
            "fixture": MCPServerConfig(
                type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
            )
        },
        ToolRegistry(),
    )
    operation = asyncio.create_task(
        provider.connect()
        if entry == "connect"
        else provider._refresh_terminated_server("fixture", "mcp_fixture_probe", SimpleNamespace())
    )
    closing = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        closing = asyncio.create_task(provider.aclose())
        await asyncio.sleep(0)
        assert provider._closing
        release.set()
        await asyncio.gather(operation, closing)
        transport.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(
            operation, *([closing] if closing is not None else []), return_exceptions=True
        )
        await provider.aclose()


async def test_shutdown_while_retiring_an_old_session_does_not_reconnect(monkeypatch):
    from cirno_core.agent.tools.mcp.connections import OwnedMCPConnection

    requested = asyncio.Event()
    started = asyncio.Event()
    release = asyncio.Event()

    async def owner():
        await requested.wait()
        started.set()
        await release.wait()

    owned = asyncio.create_task(owner())
    transport = AsyncMock(return_value={})
    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", transport)
    provider = MCPProvider({"fixture": MCPServerConfig(command="fixture")}, ToolRegistry())
    provider._connections["fixture"] = OwnedMCPConnection(owned, requested)
    operation = asyncio.create_task(
        provider._refresh_terminated_server("fixture", "mcp_fixture_probe", SimpleNamespace())
    )
    closing = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        closing = asyncio.create_task(provider.aclose())
        await asyncio.sleep(0)
        assert provider._closing
        release.set()
        await asyncio.gather(operation, closing)
        transport.assert_not_awaited()
        assert owned.done()
    finally:
        release.set()
        requested.set()
        await asyncio.gather(
            operation, owned, *([closing] if closing is not None else []), return_exceptions=True
        )
        await provider.aclose()
