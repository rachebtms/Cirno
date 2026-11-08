"""A failed lease must not leave an unowned Dream agent running."""

import asyncio
import sqlite3

import pytest

from cirno_core.memory import leases
from cirno_memory.repository import MemoryRepository


@pytest.mark.parametrize("failure", ["ownership_lost", "database_unavailable"])
async def test_renewal_failure_stops_the_provider_and_surfaces_error(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(leases, "_RENEW_INTERVAL_SECONDS", 0.001)
    stopped = asyncio.Event()

    def renew(*args, **kwargs):
        if failure == "database_unavailable":
            raise sqlite3.OperationalError("database unavailable")
        return 0

    monkeypatch.setattr(MemoryRepository, "renew", renew)

    async def provider():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    error = sqlite3.OperationalError if failure == "database_unavailable" else RuntimeError
    with pytest.raises(error, match="unavailable|no longer owned"):
        await asyncio.wait_for(leases.run_with_dream_lease(provider(), "owned-batch", tmp_path), 2)
    assert stopped.is_set()


async def test_cancelled_dream_drains_provider_before_returning(tmp_path):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def provider():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            stopped.set()

    task = asyncio.create_task(leases.run_with_dream_lease(provider(), "owned-batch", tmp_path))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()


async def test_successful_dream_returns_provider_response(tmp_path):
    async def provider():
        return "confirmed checkpoint"

    assert await leases.run_with_dream_lease(provider(), "owned-batch", tmp_path) == "confirmed checkpoint"
