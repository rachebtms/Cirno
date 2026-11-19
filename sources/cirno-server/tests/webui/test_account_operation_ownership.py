"""Accepted account work remains owned and rechecks authorization after queuing."""

import asyncio
import hashlib
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_server.webui.auth.routes import BrowserAuth
from cirno_server.webui.auth.store import AccountStore


def request(action, body=None, token=""):
    data = json.dumps(body or {}).encode()

    async def chunks(_size):
        yield data

    return SimpleNamespace(method="POST", path="/v0/auth/" + action, host="fixture",
                           headers={"Cookie": "cirno_session=" + token}, content_type="application/json",
                           content_length=len(data), content=SimpleNamespace(iter_chunked=chunks), secure=False)


@pytest.fixture
def owner(tmp_path, monkeypatch):
    # Test account transactions and token rules, without repeated scrypt work.
    monkeypatch.setattr("cirno_server.webui.auth.store._password_hash", lambda text, salt: hashlib.sha256(salt + text.encode()).digest())
    store = AccountStore(tmp_path / "account.sqlite3")
    token = store.register("owner", "FixturePassword!")
    return store, token


@pytest.mark.parametrize("action,method", [("change-password", "change_password"), ("logout", "logout"), ("complete", "complete_onboarding")])
async def test_account_cancellation_waits_for_accepted_local_mutation(owner, monkeypatch, action, method):
    store, token = owner
    auth = BrowserAuth(store, enabled=True)
    entered, release, finished = asyncio.Event(), threading.Event(), threading.Event()
    original = getattr(store, method)
    loop = asyncio.get_running_loop()

    def delayed(*args, **kwargs):
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(store, method, delayed)
    task = asyncio.create_task(auth.handle(request(action, {
        "current_password": "FixturePassword!", "new_password": "ReplacementPassword!",
    }, token)))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done, "Account request abandoned an accepted SQLite worker"
        if action != "logout":
            assert auth._lock.locked()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 1)
    assert task.cancelled()


@pytest.mark.parametrize("action", ["change-router-name", "complete"])
async def test_waiting_account_operation_rechecks_a_revoked_browser_session(owner, action):
    store, token = owner
    router = SimpleNamespace(rename=AsyncMock(return_value={"name": "fixture", "id": "id"}), wake=AsyncMock())
    auth = BrowserAuth(store, enabled=True, router=router)
    waiting = asyncio.Event()

    class QueueLock:
        def __init__(self):
            self.lock = asyncio.Lock()

        async def __aenter__(self):
            waiting.set()
            await self.lock.acquire()

        async def __aexit__(self, *_args):
            self.lock.release()

    auth._lock = queued = QueueLock()
    await queued.lock.acquire()
    task = asyncio.create_task(auth.handle(request(action, {"router_handle": "fixture", "wake": True}, token)))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        store.logout(token)
    finally:
        queued.lock.release()
    response = await task
    assert response.status == 401
    assert json.loads(response.body) == {"error": "unauthorized"}
    router.rename.assert_not_awaited()
    router.wake.assert_not_awaited()


async def test_account_lifecycle_keeps_response_and_revocation_semantics_without_a_listener(owner):
    store, first = owner
    auth = BrowserAuth(store, enabled=True)
    second = store.login("owner", "FixturePassword!")
    changed = await auth.handle(request("change-password", {
        "current_password": "FixturePassword!", "new_password": "ReplacementPassword!",
    }, first))
    assert changed.status == 200 and json.loads(changed.body) == {"ok": True}
    assert changed.headers["Cache-Control"] == "no-store"
    assert store.authenticated(first) and not store.authenticated(second)
    rejected = await auth.handle(request("login", {"username": "owner", "password": "FixturePassword!"}))
    assert rejected.status == 401 and json.loads(rejected.body) == {"error": "invalid_credentials"}
    login = await auth.handle(request("login", {"username": "owner", "password": "ReplacementPassword!"}))
    assert login.status == 200
    replacement = login.cookies["cirno_session"].value
    assert store.authenticated(replacement)
    complete = await auth.handle(request("complete", {"wake": False}, replacement))
    assert complete.status == 200 and store.owner() == ("owner", True)
    logout = await auth.handle(request("logout", token=replacement))
    assert logout.status == 200 and not store.authenticated(replacement)
    assert store.authenticated(first)


async def test_router_unavailable_does_not_bypass_the_unauthorized_response(owner):
    store, _ = owner
    response = await BrowserAuth(store, enabled=True).handle(request("change-router-name", {"router_handle": "fixture"}))
    assert response.status == 401 and json.loads(response.body) == {"error": "unauthorized"}
