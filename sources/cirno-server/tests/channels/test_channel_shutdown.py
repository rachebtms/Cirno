"""Each transport must begin closing even if another transport hangs."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.manager import ChannelManager


async def test_hanging_transport_does_not_defer_other_transport_cleanup(tmp_path):
    manager = ChannelManager(
        Config.model_validate({"channels": {"websocket": {"enabled": False}}}),
        MessageBus(), config_path=tmp_path / "config.json",
    )
    entered, release, other_stopped = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hang():
        entered.set()
        await release.wait()

    async def stop_other():
        other_stopped.set()

    manager.runtimes.channels = {
        "hanging": MagicMock(spec=BaseChannel, stop=AsyncMock(side_effect=hang)),
        "other": MagicMock(spec=BaseChannel, stop=AsyncMock(side_effect=stop_other)),
    }
    stopping = asyncio.create_task(manager.stop_all())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(other_stopped.wait(), 1)
        assert not stopping.done()
    finally:
        release.set()
        await asyncio.wait_for(stopping, 2)
