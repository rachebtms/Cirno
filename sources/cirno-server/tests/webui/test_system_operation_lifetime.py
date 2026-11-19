"""Owned installation/configuration work settles before cancellation is released."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.runtime.admission import RuntimeBusyError
from cirno_server.webui.settings.contracts import SettingsRequest
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices
from cirno_server.webui.settings.system import SystemSettingsHandler, SystemSettingsOperations


def environment(tmp_path, action):
    bus = MessageBus()
    settings = WebUISettingsServices.create(tmp_path / "config.json")
    handler = SystemSettingsHandler(settings, MagicMock(), bus.admission)
    entered, release, finished = (threading.Event() for _ in range(3))
    applied = []

    def payload():
        return {"features": [{"name": "telegram", "type": "channel", "enabled": False}],
                "requires_restart": True, "last_action": {"message": "Saved"}}

    def slow(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(3)
            return ["token"] if action == "channel-configure" else payload()
        finally:
            finished.set()

    async def activate(change, name, instance):
        applied.append(change)
        return {"handled": True, "ok": True, "requires_restart": False}

    values = {name: MagicMock() for name in SystemSettingsOperations.__dataclass_fields__}
    values.update(
        cirno_features_action=slow if action.startswith("features-") else lambda *args, **kwargs: payload(),
        cirno_features_payload=lambda **kwargs: payload(), cli_apps_action=slow,
        channel_feature_action=activate, channel_runtime_status=None,
        cirno_feature_instance_target=lambda _: None,
    )
    handler._save_channel_config_values = slow
    return SimpleNamespace(bus=bus, settings=settings, handler=handler, operations=SystemSettingsOperations(**values),
                           entered=entered, release=release, finished=finished, applied=applied)


@pytest.mark.parametrize("action", [
    "features-enable", "features-disable", "channel-configure",
    "cli-install", "cli-update", "cli-uninstall", "cli-test",
])
async def test_cancelled_system_operation_retains_worker_and_application(tmp_path, action):
    state = environment(tmp_path, action)
    query = {"name": ["telegram"]}
    if action == "features-enable":
        query["install_only"] = ["true"]
    if action == "channel-configure":
        query["enable"] = ["true"]

    async def request():
        with state.bus.admission.activity():
            return await state.handler.handle(action, SettingsRequest(query=query, payload={"values": {"token": "fixture"}}), state.operations)

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(state.entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Accepted installer/config writer was abandoned"
        with pytest.raises(RuntimeBusyError):
            with state.bus.admission.pause_if_idle(lambda: False):
                pytest.fail("Maintenance entered during accepted system work")
        state.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state.finished.is_set()
        if action == "features-enable":
            assert state.handler.features.pending_restarts == {"telegram"}
        if action in {"features-disable", "channel-configure"}:
            assert state.applied == ["disable" if action == "features-disable" else "enable"]
    finally:
        state.release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(state.finished.wait, 2)
        await state.handler.close()


@pytest.mark.parametrize("action", ["features-enable", "channel-configure"])
async def test_cancelled_system_route_records_restart_state(tmp_path, action):
    state = environment(tmp_path, action)
    router = WebUISettingsRouter(
        settings=state.settings, bus=state.bus, logger=MagicMock(), check_api_token=lambda _: True,
        parse_query=lambda path: parse_qs(urlsplit(path).query),
        json_response=lambda data: data, error_response=lambda status, message: {"status": status, "error": message},
    )
    router._system = state.handler
    router._system_operations = lambda: state.operations
    path = "/v0/settings/cirno-features/enable" if action == "features-enable" else "/v0/settings/channels/configure"
    request = SimpleNamespace(path=path, headers={}, _cirno_webui_mutation_request=True)
    request._cirno_webui_mutation_payload = (
        {"name": "telegram", "install_only": True} if action == "features-enable"
        else {"name": "telegram", "values": {"token": "fixture"}, "enable": False}
    )
    task = asyncio.create_task(router.dispatch(None, request, path))
    try:
        assert await asyncio.to_thread(state.entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        state.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert router._with_restart_state({"requires_restart": False})["requires_restart"] is True
    finally:
        state.release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(state.finished.wait, 2)
        await router.close()
