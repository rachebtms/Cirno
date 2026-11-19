"""Capability writes retain serialization without blocking the server loop."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeAdmission, RuntimeBusyError
from cirno_server.webui.settings.capabilities import (
    CapabilitySettingsHandler,
    CapabilitySettingsOperations,
)
from cirno_server.webui.settings.contracts import SettingsRequest, WebUISettingsError
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.mark.parametrize("action", ["web-search-update", "network-update", "invalid"])
async def test_capability_write_keeps_loop_responsive_and_retains_result(tmp_path, action):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_bytes()
    started, finished, release = threading.Event(), threading.Event(), threading.Event()

    def mutation(query, *, config_path):
        started.set()
        try:
            release.wait(1)
            assert query == {"fixture": ["value"]}
            if action == "invalid":
                raise WebUISettingsError("Fixture validation failed", status=409)
            config = load_config(config_path)
            config.tools.web.search.timeout = 31
            save_config(config, config_path)
            return {"saved": True}
        finally:
            finished.set()

    services = WebUISettingsServices.create(path)
    handler = CapabilitySettingsHandler(services, MagicMock())
    operations = CapabilitySettingsOperations(mutation, mutation, MagicMock())
    task = asyncio.create_task(handler.handle(
        "web-search-update" if action == "invalid" else action,
        SettingsRequest(query={"fixture": ["value"]}), operations,
    ))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert not finished.is_set(), "Serialized settings write blocked the event loop"
        release.set()
        result = await task
        if action == "invalid":
            assert result.status == 409
            assert result.error == "Fixture validation failed"
            assert path.read_bytes() == before
        else:
            assert result.payload == {"saved": True}
            assert load_config(path).tools.web.search.timeout == 31
            assert result.restart_section == ("browser" if action == "web-search-update" else "runtime")
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("late_failure", [False, True])
async def test_cancelled_capability_save_keeps_its_worker_owned(tmp_path, late_failure):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    entered, release, finished = (threading.Event() for _ in range(3))

    def mutation(query, *, config_path):
        entered.set()
        try:
            assert release.wait(3)
            if late_failure:
                raise WebUISettingsError("save failed after cancellation", status=500)
            return {"saved": True}
        finally:
            finished.set()

    handler = CapabilitySettingsHandler(WebUISettingsServices.create(path), MagicMock())
    operations = CapabilitySettingsOperations(mutation, mutation, MagicMock())
    admission = RuntimeAdmission()

    async def request():
        with admission.activity():
            return await handler.handle("network-update", SettingsRequest(query={}), operations)

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Cancellation abandoned a settings writer"
        with pytest.raises(RuntimeBusyError):
            with admission.pause_if_idle(lambda: False):
                pytest.fail("Maintenance entered before settings writer finished")
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        with admission.pause_if_idle(lambda: False):
            assert admission.paused
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
