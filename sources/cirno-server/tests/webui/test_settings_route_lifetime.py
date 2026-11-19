"""Cancelled settings requests retain commit, refresh and restart bookkeeping."""

import asyncio
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeBusyError
from cirno_server.webui.settings import profiles
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.mark.parametrize("kind", ["runtime", "model", "profile"])
async def test_cancelled_settings_route_settles_the_entire_edit(tmp_path, monkeypatch, kind):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    refreshed = []
    router = WebUISettingsRouter(
        settings=WebUISettingsServices.create(path, refresh_runtime_config=lambda: refreshed.append(True)),
        bus=MessageBus(), logger=MagicMock(), check_api_token=lambda _: True,
        parse_query=lambda value: parse_qs(urlsplit(value).query),
        json_response=lambda payload: payload,
        error_response=lambda status, message: {"status": status, "error": message},
    )
    committed, release, finished = (threading.Event() for _ in range(3))

    def wait_after_commit():
        committed.set()
        try:
            assert release.wait(3)
        finally:
            finished.set()

    def mutate(values, *, config_path):
        config = load_config(config_path)
        config.network.request_timeout_s = 121
        save_config(config, config_path)
        wait_after_commit()
        return {"requires_restart": True}

    if kind == "runtime":
        operations = replace(router._system_operations(), update_runtime_config=mutate)
        monkeypatch.setattr(router, "_system_operations", lambda: operations)
        route = "/v0/settings/runtime-config/update"
        payload = {"values": {"network.request_timeout_s": 121}}
    elif kind == "model":
        operations = replace(router._connection_operations(), update_agent=mutate)
        monkeypatch.setattr(router, "_connection_operations", lambda: operations)
        route = "/v0/settings/update"
        payload = {"timezone": "UTC"}
    else:
        original = profiles.update_profile

        def update(*args):
            saved = original(*args)
            wait_after_commit()
            return saved

        monkeypatch.setattr(profiles, "update_profile", update)
        route = "/v0/settings/profile/update"
        payload = {"name": "soul", "content": "Saved owner instructions", "revision": profiles.profile_payload("soul")["revision"]}
    request = SimpleNamespace(path=route, headers={})
    request._cirno_webui_mutation_request = True
    request._cirno_webui_mutation_payload = payload

    async def dispatch():
        with router.bus.admission.activity():
            return await router.dispatch(None, request, route)

    task = asyncio.create_task(dispatch())
    try:
        assert await asyncio.to_thread(committed.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Settings request abandoned accepted work"
        with pytest.raises(RuntimeBusyError):
            with router.bus.admission.pause_if_idle(lambda: False):
                pytest.fail("Settings writer released admission too early")
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        if kind == "profile":
            assert profiles.profile_payload("soul")["content"] == "Saved owner instructions"
        else:
            assert load_config(path).network.request_timeout_s == 121
            assert router._with_restart_state({"requires_restart": False})["requires_restart"] is True
        assert refreshed == ([True] if kind == "model" else [])
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        if committed.is_set():
            assert await asyncio.to_thread(finished.wait, 2)
        await router.close()
