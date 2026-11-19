"""Transport teardown stays attached until every accepted close settles."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.providers.openai_responses import ResponsesBackend
from cirno_core.providers.openai_responses.websocket import ResponsesWebSocketSession


@pytest.mark.parametrize("through_pool", [False, True])
async def test_socket_close_drains_repeated_cancellation(through_pool):
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def close():
        entered.set()
        try:
            await release.wait()
        finally:
            settled.set()

    session = ResponsesWebSocketSession()
    session._connection = SimpleNamespace(close=close)
    backend = ResponsesBackend()
    backend._sessions["fixture"] = session
    owner = asyncio.create_task(backend.aclose() if through_pool else session.aclose())
    try:
        await entered.wait()
        owner.cancel()
        await asyncio.sleep(0)
        owner.cancel()
        await asyncio.sleep(0)
        assert not owner.done()
        assert not settled.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await owner
        assert settled.is_set()
        assert session._connection is None
    finally:
        release.set()
        await asyncio.gather(owner, return_exceptions=True)


@pytest.mark.parametrize("through_pool", [False, True])
async def test_successful_close_releases_transport_once(through_pool):
    close = AsyncMock()
    session = ResponsesWebSocketSession()
    session._connection = SimpleNamespace(close=close)
    backend = ResponsesBackend()
    backend._sessions["fixture"] = session
    owner = backend if through_pool else session
    await owner.aclose()
    await owner.aclose()
    close.assert_awaited_once()
    assert session._connection is None


async def test_pool_close_waits_for_peers_before_propagating_failure():
    entered, failed, release, settled = (asyncio.Event() for _ in range(4))
    backend = ResponsesBackend()
    failure = RuntimeError("fixture close failed")

    async def fail():
        await entered.wait()
        failed.set()
        raise failure

    async def close():
        entered.set()
        await release.wait()
        settled.set()

    backend._sessions.update(
        {
            "failed": SimpleNamespace(aclose=fail),
            "pending": SimpleNamespace(aclose=close),
        }
    )
    owner = asyncio.create_task(backend.aclose())
    try:
        await failed.wait()
        for _ in range(5):
            await asyncio.sleep(0)
        assert not owner.done()
        release.set()
        with pytest.raises(RuntimeError) as exc:
            await owner
        assert exc.value is failure
        assert settled.is_set()
    finally:
        release.set()
        await asyncio.gather(owner, return_exceptions=True)


async def test_pool_close_drains_repeated_cancellation():
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    backend = ResponsesBackend()

    async def close():
        entered.set()
        await release.wait()
        settled.set()

    backend._sessions["pending"] = SimpleNamespace(aclose=close)
    owner = asyncio.create_task(backend.aclose())
    try:
        await entered.wait()
        owner.cancel()
        await asyncio.sleep(0)
        owner.cancel()
        await asyncio.sleep(0)
        assert not owner.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await owner
        assert settled.is_set()
        assert not backend._sessions
    finally:
        release.set()
        await asyncio.gather(owner, return_exceptions=True)
