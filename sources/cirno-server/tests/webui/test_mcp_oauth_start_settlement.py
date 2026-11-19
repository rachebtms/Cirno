"""OAuth preparation owns accepted disk work without starting a cancelled flow."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_core.runtime.admission import RuntimeBusyError
from cirno_server.webui.settings import routes
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.fixture
def router(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    return routes.WebUISettingsRouter(
        settings=WebUISettingsServices.create(path), bus=MessageBus(), logger=MagicMock(),
        check_api_token=lambda _: True,
        parse_query=lambda value: parse_qs(urlsplit(value).query),
        json_response=lambda value: value,
        error_response=lambda status, message: {"status": status, "error": message},
        mcp_oauth_redirect_uri=lambda _: "http://gateway.test/v0/mcp/oauth/callback",
    )


async def dispatch(router, name="fixture"):
    path = "/v0/settings/mcp-oauth/start"
    request = SimpleNamespace(path=path, headers={}, _cirno_webui_mutation_request=True,
                              _cirno_webui_mutation_payload={"name": name})
    with router.bus.admission.activity():
        return await router.dispatch(None, request, path)


async def test_invalid_callback_does_not_materialize_configuration(router, monkeypatch):
    ensure = MagicMock(side_effect=RuntimeError("must not write"))
    monkeypatch.setattr(routes, "ensure_mcp_oauth_server", ensure)
    router._mcp_oauth_redirect_uri = lambda _: "file:///bad"
    try:
        result = await dispatch(router)
        assert result["status"] == 400
        ensure.assert_not_called()
    finally:
        await router.close()


@pytest.mark.parametrize("changed,fail", [(True, False), (True, True), (False, False)])
async def test_cancelled_preparation_settles_write_and_restart_state(
    router, monkeypatch, changed, fail
):
    loop = asyncio.get_running_loop()
    main_thread = threading.get_ident()
    entered = asyncio.Event()
    release, finished = threading.Event(), threading.Event()
    if not changed:
        config = load_config(router.settings.config.path)
        config.tools.mcp_servers["fixture"] = MCPServerConfig(
            type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
        )
        save_config(config, router.settings.config.path)

    def ensure(_query, *, config_path):
        assert threading.get_ident() != main_thread
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2)
            config = load_config(config_path)
            config.tools.mcp_servers["fixture"] = MCPServerConfig(
                type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
            )
            save_config(config, config_path)
            if fail:
                raise OSError("failure after config replacement")
            return "fixture", config.tools.mcp_servers["fixture"], config.network
        finally:
            finished.set()

    monkeypatch.setattr(routes, "ensure_mcp_oauth_server", ensure)
    start = AsyncMock()
    router._mcp_oauth.start = start
    task = asyncio.create_task(dispatch(router))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Accepted disk work was detached on cancellation"
        with pytest.raises(RuntimeBusyError), router.bus.admission.pause_if_idle(lambda: False):
            pytest.fail("Accepted write must retain admission")
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 2)
        with pytest.raises(asyncio.CancelledError):
            await task
        await router.close()
    start.assert_not_awaited()
    assert "fixture" in load_config(router.settings.config.path).tools.mcp_servers
    assert bool(router._with_restart_state({}).get("requires_restart")) is changed


async def test_original_manual_callback_is_preserved_and_reload_clears_only_own_reason(
    router, monkeypatch
):
    def ensure(_query, *, config_path):
        config = load_config(config_path)
        cfg = MCPServerConfig(type="streamableHttp", auth="oauth", url="https://fixture.test/mcp")
        config.tools.mcp_servers["fixture"] = cfg
        save_config(config, config_path)
        return "fixture", cfg, config.network

    monkeypatch.setattr(routes, "ensure_mcp_oauth_server", ensure)
    start = AsyncMock(return_value={"status": "authorization_required"})
    router._mcp_oauth.start = start
    router._restart_changes["unrelated"] = "runtime"
    try:
        payload = await dispatch(router)
        assert start.await_args.args[2] == "http://gateway.test/v0/mcp/oauth/callback"
        assert payload["requires_restart"]
        assert len(router._restart_changes) == 2
        router._mcp_reload = AsyncMock(return_value={"ok": True, "requires_restart": False})
        await router._reload_mcp_runtime()
        assert router._restart_changes == {"unrelated": "runtime"}
    finally:
        await router.close()


@pytest.mark.parametrize("result", [
    {"ok": False}, {"ok": True, "requires_restart": True},
])
async def test_unsuccessful_reload_retains_materialization_restart_reason(router, result):
    router._restart_changes[routes._MCP_OAUTH_RESTART_REASON] = "runtime"
    router._mcp_reload = AsyncMock(return_value=result)
    try:
        await router._reload_mcp_runtime()
        assert router._restart_changes == {routes._MCP_OAUTH_RESTART_REASON: "runtime"}
    finally:
        await router.close()


async def test_reload_does_not_clear_a_newer_oauth_materialization(router):
    entered, release = asyncio.Event(), asyncio.Event()

    async def reload():
        entered.set()
        await release.wait()
        return {"ok": True, "requires_restart": False}

    router._mcp_reload = reload
    router._restart_changes[routes._MCP_OAUTH_RESTART_REASON] = "runtime"
    task = asyncio.create_task(router._reload_mcp_runtime())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        router._mcp_oauth_config_generation += 1
    finally:
        release.set()
        await task
        await router.close()
    assert router._restart_changes == {routes._MCP_OAUTH_RESTART_REASON: "runtime"}


async def test_real_preset_materialization_and_unchanged_reauthorization(router):
    router._mcp_oauth.start = AsyncMock(return_value={"status": "authorization_required"})
    try:
        result = await dispatch(router, "xmind")
        assert result["requires_restart"]
        config = load_config(router.settings.config.path)
        assert config.tools.mcp_servers["xmind"].auth == "oauth"
        router._restart_changes.clear()
        result = await dispatch(router, "xmind")
        assert not result.get("requires_restart")
    finally:
        await router.close()


@pytest.mark.parametrize("write", [False, True])
async def test_failed_preparation_preserves_changed_state_without_exposing_error(
    router, monkeypatch, write
):
    def ensure(_query, *, config_path):
        if write:
            config = load_config(config_path)
            config.tools.mcp_servers["fixture"] = MCPServerConfig(
                type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
            )
            save_config(config, config_path)
        raise OSError("secret failure detail")

    monkeypatch.setattr(routes, "ensure_mcp_oauth_server", ensure)
    router._mcp_oauth.start = AsyncMock()
    try:
        result = await dispatch(router)
        assert result == {"status": 500, "error": "MCP OAuth start failed"}
        router._mcp_oauth.start.assert_not_awaited()
        assert bool(router._with_restart_state({}).get("requires_restart")) is write
    finally:
        await router.close()
