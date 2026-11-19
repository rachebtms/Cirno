"""Accepted OAuth writes retain ownership through cancellation and refresh cleanup."""

import asyncio
import threading

import httpx
import pytest
from cirno_core.agent.tools.mcp_oauth import MCPOAuthStorage, create_mcp_oauth_auth
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken


def _hold_write(monkeypatch, storage, method, *, fails=False):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    original = getattr(storage, method)

    def write(*args, **kwargs):
        loop.call_soon_threadsafe(started.set)
        try:
            if not release.wait(timeout=2):
                raise AssertionError("Fixture did not release the OAuth write")
            if fails:
                raise OSError("Fixture write failed")
            return original(*args, **kwargs)
        finally:
            completed.set()

    monkeypatch.setattr(storage, method, write)
    return started, release, completed


@pytest.mark.parametrize("operation", ["tokens", "claim", "clear"])
@pytest.mark.parametrize("fails", [False, True])
async def test_cancelled_oauth_mutation_waits_for_accepted_write(
    tmp_path, monkeypatch, operation, fails
):
    storage = MCPOAuthStorage(
        "fixture", "https://fixture.test/mcp", config_path=tmp_path / "config.json"
    )
    await storage.set_tokens(OAuthToken(access_token="old-fixture-token"))
    started, release, completed = _hold_write(
        monkeypatch, storage, "_update_entry_sync", fails=fails
    )
    if operation == "tokens":
        mutation = storage.set_tokens(OAuthToken(access_token="new-fixture-token"))
    elif operation == "claim":
        mutation = storage.prepare_redirect_uri("https://fixture.test/callback")
    else:
        mutation = storage.clear_tokens_and_client()
    task = asyncio.create_task(mutation)
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        pending = not task.done()
    finally:
        release.set()
        outcomes = await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(completed.wait, 2)
    assert pending, "OAuth cancellation detached an accepted credential write"
    assert completed.is_set()
    assert isinstance(outcomes[0], asyncio.CancelledError)
    tokens = await storage.get_tokens()
    if fails or operation == "claim":
        assert tokens.access_token == "old-fixture-token"
    elif operation == "tokens":
        assert tokens.access_token == "new-fixture-token"
    else:
        assert tokens is None


async def test_cancelled_refresh_holds_its_lock_until_rotated_token_is_persisted(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.json"
    server_url = "https://fixture.test/mcp"
    storage = MCPOAuthStorage("fixture", server_url, config_path=config_path)
    await storage.set_oauth_metadata(
        OAuthMetadata.model_validate(
            {
                "issuer": "https://auth.fixture.test",
                "authorization_endpoint": "https://auth.fixture.test/authorize",
                "token_endpoint": "https://auth.fixture.test/token",
                "response_types_supported": ["code"],
            }
        )
    )
    await storage.set_tokens(
        OAuthToken(
            access_token="expired-fixture-token", refresh_token="fixture-refresh", expires_in=-1
        )
    )
    await storage.set_client_info(
        OAuthClientInformationFull(
            client_id="fixture-client", redirect_uris=["https://fixture.test/callback"]
        )
    )
    auth = await create_mcp_oauth_auth("fixture", server_url, config_path=config_path)
    owned_storage = auth._cirno_storage
    started, release, completed = _hold_write(monkeypatch, owned_storage, "_finish_refresh_sync")
    lock = owned_storage.refresh_lock()
    monkeypatch.setattr(owned_storage, "refresh_lock", lambda: lock)

    def respond(request):
        assert str(request.url) == "https://auth.fixture.test/token"
        return httpx.Response(
            200,
            json={
                "access_token": "rotated-fixture-token",
                "refresh_token": "rotated-fixture-refresh",
                "token_type": "Bearer",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), auth=auth) as client:
        task = asyncio.create_task(client.get(server_url))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            for _ in range(8):
                await asyncio.sleep(0)
            pending = not task.done()
            held = lock.is_locked
        finally:
            release.set()
            outcomes = await asyncio.gather(task, return_exceptions=True)
            assert await asyncio.to_thread(completed.wait, 2)
    assert pending and held, (
        "Cancelled refresh released its lease before persisting the rotated token"
    )
    assert completed.is_set()
    assert isinstance(outcomes[0], asyncio.CancelledError)
    assert not lock.is_locked
    tokens = await storage.get_tokens()
    assert tokens.access_token == "rotated-fixture-token"
    assert tokens.refresh_token == "rotated-fixture-refresh"
