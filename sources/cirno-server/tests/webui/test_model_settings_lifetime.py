"""Accepted model edits own both the disk commit and live runtime refresh."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeAdmission, RuntimeBusyError
from cirno_server.webui.settings.connection_contracts import ConnectionSettingsOperations
from cirno_server.webui.settings.connections import ConnectionSettingsHandler
from cirno_server.webui.settings.contracts import SettingsRequest
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.mark.parametrize(("action", "operation"), [
    ("agent-update", "update_agent"), ("model-update", "update_model"),
    ("model-create", "create_model"), ("model-delete", "delete_model"),
    ("call-order-update", "update_call_order"),
    ("provider-create", "create_provider"), ("provider-update", "update_provider"),
])
async def test_cancelled_model_edit_finishes_commit_and_refresh(tmp_path, action, operation):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    committed, release, finished = (threading.Event() for _ in range(3))
    called, refreshed = [], []
    owner_thread = threading.get_ident()

    def make_operation(name):
        def mutate(query, *, config_path):
            called.append(name)
            config = load_config(config_path)
            config.network.request_timeout_s = 121
            save_config(config, config_path)
            committed.set()
            try:
                assert release.wait(3)
                return {"requires_restart": False}
            finally:
                finished.set()
        return mutate

    def refresh():
        assert threading.get_ident() == owner_thread
        refreshed.append(load_config(path).network.request_timeout_s)

    operations = ConnectionSettingsOperations(**{
        name: make_operation(name) for name in ConnectionSettingsOperations.__dataclass_fields__
    })
    settings = WebUISettingsServices.create(path, refresh_runtime_config=refresh)
    admission = RuntimeAdmission()
    handler = ConnectionSettingsHandler(settings, MagicMock(), admission)

    async def request():
        with admission.activity():
            return await handler.handle(action, SettingsRequest(query={}), operations)

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(committed.wait, 2)
        assert refreshed == []
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "A saved model edit lost its runtime-refresh owner"
        with pytest.raises(RuntimeBusyError):
            with admission.pause_if_idle(lambda: False):
                pytest.fail("Pending model edit was reported idle")
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert called == [operation]
        assert refreshed == [121]
        assert finished.is_set()
        with admission.pause_if_idle(lambda: False):
            assert admission.paused
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
        await handler.close()
