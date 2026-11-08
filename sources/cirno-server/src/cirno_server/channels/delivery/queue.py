"""Bounded destination queues; unrelated conversations can deliver concurrently."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.session.manager import SessionManager
from loguru import logger

from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.durable import DurableDelivery
from cirno_server.channels.delivery.retry import RetrySender

SEND_CONCURRENCY = 32
PENDING_LIMIT = 256


class OutboundQueue:
    def __init__(
        self,
        bus: MessageBus,
        config_path: Path,
        sessions: SessionManager | None,
        config: Callable[[], Config],
        channel: Callable[[str], BaseChannel | None],
        is_stopping: Callable[[str], bool],
    ) -> None:
        self.channel = channel
        self.is_stopping = is_stopping
        self.tasks: dict[asyncio.Task[None], tuple[str, str]] = {}
        self.tails: dict[tuple[str, str], asyncio.Task[None]] = {}
        self.scheduled: set[str] = set()
        self.pending_slots = asyncio.Semaphore(PENDING_LIMIT)
        self.send_slots = asyncio.Semaphore(SEND_CONCURRENCY)
        self.retry = RetrySender(self.send_slots, lambda: config().channels.send_max_retries)
        self.durable = DurableDelivery(bus, config_path, sessions, config)

    async def cancel(self, channel: str | None = None) -> None:
        tasks = [task for task, key in self.tasks.items() if channel is None or key[0] == channel]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def queue(self, channel: BaseChannel, msg: OutboundMessage) -> None:
        """Bound scheduled sends; preserve FIFO per destination, not across chats.

        Retry waits retain their destination tail and admission, not a send permit.
        Saturation pauses dispatch rather than creating unbounded tasks or dropping messages.
        """
        if msg.delivery_id in self.scheduled:
            return
        if isinstance(msg.event, ProgressEvent) and msg.event.tool_events:
            msg = channel.prepare_tool_events(msg)
        await self.pending_slots.acquire()
        if self.is_stopping(msg.channel) or self.channel(msg.channel) is not channel:
            self.pending_slots.release()
            return
        key = (msg.channel, msg.chat_id)
        previous = self.tails.get(key)
        if msg.delivery_id is not None:
            self.scheduled.add(msg.delivery_id)

        async def send() -> None:
            if previous is not None:
                await asyncio.shield(asyncio.gather(previous, return_exceptions=True))
            if msg.delivery_id is not None:
                # Acquire before claiming: queued cancellation must remain pending.
                async with self.send_slots:
                    await self.durable.send(channel, msg)
            else:
                await self.retry.send(channel, msg)

        task = asyncio.create_task(send(), name=f"outbound-{msg.channel}-{msg.chat_id}")
        self.tasks[task] = key
        self.tails[key] = task

        def finished(done: asyncio.Task[None]) -> None:
            self.tasks.pop(done, None)
            if msg.delivery_id is not None:
                self.scheduled.discard(msg.delivery_id)
            if self.tails.get(key) is done:
                self.tails.pop(key, None)
            self.pending_slots.release()
            if not done.cancelled() and (error := done.exception()) is not None:
                logger.error("Outbound delivery to {}:{} failed: {}", *key, error)

        task.add_done_callback(finished)
