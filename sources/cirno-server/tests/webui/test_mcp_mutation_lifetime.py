"""MCP writes, runtime application and restart state share request ownership."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeBusyError
from cirno_server.webui.mcp import actions
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.mark.parametrize("action", ["enable", "disable", "remove", "proxy", "custom", "import", "import-cursor", "tools", "reconnect"])
@pytest.mark.parametrize("stage", ["write", "reload"])
async def test_cancelled_mcp_route_retains_write_reload_and_restart_state(tmp_path, monkeypatch, action, stage):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    started = asyncio.Event()
    release_write = threading.Event()
    release_reload = asyncio.Event()
    applied = []
    loop = asyncio.get_running_loop()

    def mutate(*args, config_path):
        config = load_config(config_path)
        config.network.request_timeout_s = 122
        save_config(config, config_path)
        if stage == "write":
            loop.call_soon_threadsafe(started.set)
            assert release_write.wait(2)
        return {"presets": [], "installed_count": 0, "requires_restart": True}

    async def reload_mcp():
        if stage == "reload":
            started.set()
            await release_reload.wait()
        applied.append(load_config(path).network.request_timeout_s)
        return {"ok": False, "message": "Fixture restart required", "requires_restart": True}

    for name in ("mcp_presets_action", "custom_mcp_action", "mcp_reconnect_action"):
        monkeypatch.setattr(actions, name, mutate)
    router = WebUISettingsRouter(
        settings=WebUISettingsServices.create(path), bus=MessageBus(), logger=MagicMock(),
        check_api_token=lambda _: True, parse_query=lambda value: parse_qs(urlsplit(value).query),
        json_response=lambda value: value,
        error_response=lambda status, message: {"status": status, "error": message},
        mcp_reload=reload_mcp,
    )
    route = f"/v0/settings/mcp-presets/{action}"
    request = SimpleNamespace(path=route, headers={}, _cirno_webui_mutation_request=True,
                              _cirno_webui_mutation_payload={"name": "fixture"})

    async def dispatch():
        with router.bus.admission.activity():
            return await router.dispatch(None, request, route)

    operation = asyncio.create_task(dispatch())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        operation.cancel()
        await asyncio.sleep(0)
        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done(), "MCP request abandoned its accepted write or reload"
        with pytest.raises(RuntimeBusyError), router.bus.admission.pause_if_idle(lambda: False):
            pytest.fail("MCP mutation released maintenance admission too early")
        release_write.set()
        release_reload.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
        assert applied == [122]
        assert router._with_restart_state({})["restart_required_sections"] == ["runtime"]
    finally:
        release_write.set()
        release_reload.set()
        await asyncio.gather(operation, return_exceptions=True)
        await router.close()
