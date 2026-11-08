"""Stop drains inbound and typing work before closing the shared Bot API pools."""

import asyncio
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.channels.telegram.runtime import TelegramChannel


@pytest.mark.asyncio
@pytest.mark.parametrize("task_map", ["typing", "_inbound_workers", "_media_group_tasks"])
async def test_stop_waits_for_owned_worker_cleanup(task_map):
    channel = TelegramChannel(TelegramConfig(), MessageBus())
    entered, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    channel._teardown_app = AsyncMock()

    async def worker():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closing.set()
            await release.wait()

    task = asyncio.create_task(worker())
    owned = channel.presence.tasks if task_map == "typing" else getattr(channel, task_map)
    owned["personal"] = task
    await entered.wait()
    stop = asyncio.create_task(channel.stop())
    try:
        await asyncio.wait_for(closing.wait(), timeout=1)
        assert not stop.done()
        channel._teardown_app.assert_not_awaited()
    finally:
        release.set()
        await asyncio.wait_for(stop, timeout=1)
        await asyncio.gather(task, return_exceptions=True)
    channel._teardown_app.assert_awaited_once()
    assert not owned


async def test_stop_drains_replaced_typing_worker_before_closing_transport():
    channel = TelegramChannel(TelegramConfig(), MessageBus())
    entered, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    channel._teardown_app = AsyncMock()

    async def typing_loop(chat_id):
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closing.set()
            await release.wait()

    channel.presence.typing_loop = typing_loop
    channel.presence.start_typing("123")
    await entered.wait()
    previous = channel.presence.tasks["123"]
    channel.presence.stop_typing("123")
    await closing.wait()
    stop = asyncio.create_task(channel.stop())
    try:
        await asyncio.sleep(0)
        assert not stop.done()
        channel._teardown_app.assert_not_awaited()
    finally:
        release.set()
        await asyncio.wait_for(stop, timeout=1)
        await asyncio.gather(previous, return_exceptions=True)
    channel._teardown_app.assert_awaited_once()
