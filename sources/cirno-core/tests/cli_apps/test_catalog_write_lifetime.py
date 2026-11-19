"""Cancelling a catalog refresh retains accepted disk publication until it settles."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from cirno_core.apps.cli import catalog
from cirno_core.apps.cli.contracts import CliAppsRuntimeConfig


async def test_cancelled_catalog_refresh_drains_accepted_cache_write(tmp_path, monkeypatch):
    entered, release, finished = (threading.Event() for _ in range(3))

    def write(*args):
        entered.set()
        try:
            assert release.wait(3)
        finally:
            finished.set()

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"clis": []})

    manager = catalog.RegistryCatalog(tmp_path, CliAppsRuntimeConfig())
    monkeypatch.setattr(manager, "_cached_registry", lambda path: (None, 0))
    monkeypatch.setattr(catalog.httpx, "AsyncClient", Client)
    monkeypatch.setattr(catalog.records, "_write_json", write)
    task = asyncio.create_task(manager._fetch_registry_async("https://example.invalid/registry", tmp_path / "cache.json"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Refresh discarded an accepted cache publication"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
