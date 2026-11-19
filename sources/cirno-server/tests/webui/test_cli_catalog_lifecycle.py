"""Settings owns catalog refreshes across maintenance and shutdown."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cirno_core.runtime.admission import RuntimeAdmission, RuntimeBusyError
from cirno_server.webui import cli_apps_api
from cirno_server.webui.settings.contracts import SettingsRequest
from cirno_server.webui.settings.services import WebUISettingsServices
from cirno_server.webui.settings.system import SystemSettingsHandler, SystemSettingsOperations


def environment(tmp_path, monkeypatch, name, *, cleanup_wait=False):
    started, cleanup, release = (asyncio.Event() for _ in range(3))

    async def refresh(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            if cleanup_wait:
                await release.wait()

    manager = SimpleNamespace(
        registry=SimpleNamespace(catalog_cache_fresh=lambda **kwargs: False, refresh_catalog_cache=refresh),
        payload=lambda **kwargs: {"apps": [{"name": name}], "installed_count": 0},
    )
    admission = RuntimeAdmission()
    handler = SystemSettingsHandler(WebUISettingsServices.create(tmp_path / name / "config.json"), MagicMock(), admission)
    values = {key: MagicMock() for key in SystemSettingsOperations.__dataclass_fields__}
    values["cli_apps_payload"] = cli_apps_api.cli_apps_payload
    return SimpleNamespace(manager=manager, admission=admission, handler=handler,
                           operations=SystemSettingsOperations(**values), started=started, cleanup=cleanup, release=release)


async def cleanup(state):
    state.release.set()
    await state.handler.close()


async def test_detached_catalog_refresh_blocks_maintenance_until_closed(tmp_path, monkeypatch):
    state = environment(tmp_path, monkeypatch, "first")
    monkeypatch.setattr(cli_apps_api, "_manager", lambda path: state.manager)
    try:
        response = await state.handler.handle("cli-list", SettingsRequest(query={}), state.operations)
        assert response.payload["catalog_refresh_pending"] is True
        await asyncio.wait_for(state.started.wait(), 2)
        with pytest.raises(RuntimeBusyError):
            with state.admission.pause_if_idle(lambda: False):
                pytest.fail("Maintenance ignored an active catalog writer")
        await state.handler.close()
        assert state.cleanup.is_set()
        with state.admission.pause_if_idle(lambda: False):
            pass
    finally:
        await cleanup(state)


@pytest.mark.parametrize("cancel_close", [False, True])
async def test_settings_close_drains_catalog_cleanup(tmp_path, monkeypatch, cancel_close):
    state = environment(tmp_path, monkeypatch, "first", cleanup_wait=True)
    monkeypatch.setattr(cli_apps_api, "_manager", lambda path: state.manager)
    closing = None
    try:
        await state.handler.handle("cli-list", SettingsRequest(query={}), state.operations)
        await asyncio.wait_for(state.started.wait(), 2)
        closing = asyncio.create_task(state.handler.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not closing.done(), "Settings closed while its refresh was still live"
        await asyncio.wait_for(state.cleanup.wait(), 2)
        if cancel_close:
            closing.cancel()
            await asyncio.sleep(0)
            closing.cancel()
            await asyncio.sleep(0)
            assert not closing.done(), "Cancellation discarded accepted refresh cleanup"
        state.release.set()
        if cancel_close:
            with pytest.raises(asyncio.CancelledError):
                await closing
        else:
            await closing
    finally:
        state.release.set()
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)
        await cleanup(state)


async def test_independent_settings_owners_do_not_share_refresh_or_throttle(tmp_path, monkeypatch):
    first = environment(tmp_path, monkeypatch, "first")
    second = environment(tmp_path, monkeypatch, "second")
    monkeypatch.setattr(cli_apps_api, "_manager", lambda path: first.manager if path.parent.name == "first" else second.manager)
    try:
        await first.handler.handle("cli-list", SettingsRequest(query={}), first.operations)
        await asyncio.wait_for(first.started.wait(), 2)
        await second.handler.handle("cli-list", SettingsRequest(query={}), second.operations)
        await asyncio.sleep(0)
        assert second.started.is_set(), "Second owner reused another owner's refresh task"
    finally:
        await cleanup(first)
        await cleanup(second)


async def test_repeated_close_does_not_interrupt_refresh_cleanup(tmp_path):
    from cirno_server.webui.cli_catalog_refresh import CliCatalogRefresh

    started, cleanup_entered, release = (asyncio.Event() for _ in range(3))

    async def refresh(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_entered.set()
            await release.wait()

    owner = CliCatalogRefresh(RuntimeAdmission())
    manager = SimpleNamespace(registry=SimpleNamespace(refresh_catalog_cache=refresh))
    first = second = None
    try:
        assert owner.start(manager)
        await asyncio.wait_for(started.wait(), 2)
        first = asyncio.create_task(owner.close())
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        second = asyncio.create_task(owner.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert owner.has_pending_work, "Repeated close cancelled the in-progress cleanup itself"
        release.set()
        await asyncio.gather(first, second)
    finally:
        release.set()
        await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)
        await owner.close()


async def test_refresh_starts_at_zero_clock_and_retains_per_owner_throttle(monkeypatch):
    from cirno_server.webui import cli_catalog_refresh

    clock = [0.0]
    monkeypatch.setattr(cli_catalog_refresh, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    calls = []

    async def refresh(**kwargs):
        calls.append(kwargs)

    owner = cli_catalog_refresh.CliCatalogRefresh(RuntimeAdmission())
    manager = SimpleNamespace(registry=SimpleNamespace(refresh_catalog_cache=refresh))
    try:
        assert owner.start(manager), "Initial refresh must not wait for process uptime60s"
        assert owner.start(manager), "A pending refresh is reused"
        await asyncio.sleep(0)
        assert calls == [{"force_refresh": True}]
        clock[0] = 30
        assert owner.start(manager) is False
        clock[0] = 60
        assert owner.start(manager) is True
        await asyncio.sleep(0)
        assert len(calls) == 2
        await owner.close()
        clock[0] = 180
        assert owner.start(manager) is False
    finally:
        await owner.close()


async def test_refresh_cannot_enter_paused_runtime():
    from cirno_core.runtime.admission import RuntimeMaintenanceError
    from cirno_server.webui.cli_catalog_refresh import CliCatalogRefresh

    admission = RuntimeAdmission()
    owner = CliCatalogRefresh(admission)
    manager = SimpleNamespace(registry=SimpleNamespace(refresh_catalog_cache=MagicMock()))
    try:
        with admission.pause_if_idle(lambda: False):
            with pytest.raises(RuntimeMaintenanceError):
                owner.start(manager)
        assert owner.has_pending_work is False
        manager.registry.refresh_catalog_cache.assert_not_called()
    finally:
        await owner.close()


async def test_settings_close_retains_real_catalog_cache_writer(tmp_path, monkeypatch):
    import threading

    from cirno_core.apps.cli import CliAppManager, catalog

    entered, release, finished = (threading.Event() for _ in range(3))

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"clis": []})

    def write(*args):
        entered.set()
        try:
            assert release.wait(3)
        finally:
            finished.set()

    state = environment(tmp_path, monkeypatch, "first")
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / "catalog")
    monkeypatch.setattr(cli_apps_api, "_manager", lambda path: manager)
    monkeypatch.setattr(catalog.resources, "_CATALOG_SOURCES", [
        ("fixture", "https://example.invalid/registry", "https://example.invalid/", True),
    ])
    monkeypatch.setattr(catalog.httpx, "AsyncClient", Client)
    monkeypatch.setattr(catalog.records, "_write_json", write)
    closing = None
    try:
        await state.handler.handle("cli-list", SettingsRequest(query={}), state.operations)
        assert await asyncio.to_thread(entered.wait, 2)
        closing = asyncio.create_task(state.handler.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not closing.done()
        with pytest.raises(RuntimeBusyError):
            with state.admission.pause_if_idle(lambda: False):
                pytest.fail("Maintenance entered before catalog publication settled")
        release.set()
        await closing
        assert finished.is_set()
        with state.admission.pause_if_idle(lambda: False):
            pass
    finally:
        release.set()
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)
        await state.handler.close()
        assert await asyncio.to_thread(finished.wait, 2)


async def test_paused_runtime_still_serves_cached_catalog_without_starting_refresh(tmp_path, monkeypatch):
    state = environment(tmp_path, monkeypatch, "first")
    monkeypatch.setattr(cli_apps_api, "_manager", lambda path: state.manager)
    try:
        with state.admission.pause_if_idle(lambda: False):
            result = await state.handler.handle("cli-list", SettingsRequest(query={}), state.operations)
            assert result.status == 200
            assert result.payload["apps"] == [{"name": "first"}]
            assert result.payload["catalog_refresh_pending"] is False
            assert not state.started.is_set()
    finally:
        await cleanup(state)
