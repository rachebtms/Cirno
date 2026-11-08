"""MCP shutdown drains accepted closes, including repeated caller cancellation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.mcp.connections import close_mcp_connections, OwnedMCPConnection
from loguru import logger


@pytest.mark.asyncio
async def test_failed_close_is_visible_and_does_not_skip_other_connections():
    records = []
    sink = logger.add(lambda message: records.append(message.record), level="WARNING")
    second = AsyncMock()
    try:
        await close_mcp_connections({
            "broken": SimpleNamespace(aclose=AsyncMock(side_effect=OSError("transport lost"))),
            "healthy": SimpleNamespace(aclose=second),
        })
    finally:
        logger.remove(sink)
    second.assert_awaited_once()
    assert any("connection cleanup failed (OSError)" in record["message"] for record in records)


@pytest.mark.asyncio
async def test_repeated_stop_waits_for_close_and_then_closes_remaining_connections():
    entered = asyncio.Event()
    release = asyncio.Event()
    closed = []

    async def slow_close():
        entered.set()
        await release.wait()
        closed.append("first")

    async def last_close():
        closed.append("last")

    close_requested = asyncio.Event()

    async def own_connection():
        await close_requested.wait()
        await slow_close()

    owner = asyncio.create_task(own_connection())
    task = asyncio.create_task(close_mcp_connections({
        "first": OwnedMCPConnection(owner, close_requested),
        "last": SimpleNamespace(aclose=last_close),
    }))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)
    assert closed == ["first", "last"]
