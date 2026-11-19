"""Accepted vault mutations settle before tool cancellation is acknowledged."""

import asyncio
import threading

import pytest
from cirno_core.agent.tools.credential import CredentialTool


@pytest.mark.parametrize("action", ["store", "delete"])
@pytest.mark.parametrize("fails", [False, True])
async def test_cancelled_credential_mutation_waits_for_accepted_worker(monkeypatch, action, fails):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    calls = []

    class Vault:
        def mutate(self, *args, **kwargs):
            calls.append((args, kwargs))
            loop.call_soon_threadsafe(started.set)
            try:
                if not release.wait(timeout=2):
                    raise AssertionError("Test did not release the vault worker")
                if fails:
                    raise ValueError("Fixture mutation failed")
                return {"ok": True}
            finally:
                completed.set()

        save = mutate
        delete = mutate

    monkeypatch.setattr("cirno_core.agent.tools.credential.Credentials", lambda **kwargs: Vault())
    operation = asyncio.create_task(CredentialTool().execute(action=action, id="fixture", label="Fixture", value="fixture"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        operation.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        operation.cancel()  # A second stop must not detach the accepted write either.
        await asyncio.sleep(0)
        pending_before_release = not operation.done()
    finally:
        release.set()
        outcome = await asyncio.gather(operation, return_exceptions=True)
    assert pending_before_release, "Tool cancellation left an accepted credential mutation running"
    assert completed.is_set()
    assert len(calls) == 1
    assert isinstance(outcome[0], asyncio.CancelledError)
