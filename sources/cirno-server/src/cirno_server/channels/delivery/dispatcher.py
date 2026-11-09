"""Route bus events to adapters and recover accepted durable deliveries."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import (
    ProgressEvent,
    RetryWaitEvent,
    RuntimeModelUpdatedEvent,
    StreamDeltaEvent,
    StreamEndEvent,
    StreamedResponseEvent,
)
from cirno_core.bus.queue import MessageBus
from loguru import logger

from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.coalescing import coalesce_stream_deltas
from cirno_server.channels.delivery.duplicates import OriginReplies
from cirno_server.channels.delivery.inbox import InboxDelivery
from cirno_server.channels.delivery.queue import OutboundQueue
from cirno_server.channels.outbox import RETRY_SECONDS


class OutboundDispatcher:
    def __init__(
        self,
        bus: MessageBus,
        delivery: OutboundQueue,
        notifications: InboxDelivery,
        channel: Callable[[str], BaseChannel | None],
    ) -> None:
        self.bus = bus
        self.delivery = delivery
        self.notifications = notifications
        self.channel = channel
        self.pending: list[OutboundMessage] = []
        self.dispatching = False
        self.origins = OriginReplies()

    def sends_progress(self, channel_name: str, *, tool_hint: bool = False) -> bool:
        """Return whether progress (or tool-hints) may be sent to *channel_name*."""
        ch = self.channel(channel_name)
        if ch is None:
            logger.debug("Progress check for unknown channel: {}", channel_name)
            return False
        return ch.send_tool_hints if tool_hint else ch.send_progress

    async def recover(self) -> None:
        with self.bus.admission.activity():
            for msg in await self.delivery.durable.ready():
                channel = self.channel(msg.channel)
                if channel is None:
                    await self.delivery.durable.finish(msg, "failed", "channel_disabled")
                else:
                    await self.notifications.record(msg)
                    await self.delivery.queue(channel, msg)
            # Recover accepted messages first: a full queue must be able to
            # drain before admitting more Inbox notifications.
            await self.notifications.queue_telegram()

    async def run(self) -> None:
        try:
            await self.bus.admission.wait_until_open()
            await self._run()
        finally:
            await self.delivery.cancel()

    async def _run(self) -> None:
        """Dispatch outbound messages to the appropriate channel."""
        logger.info("Outbound dispatcher started")

        # Buffer for messages that couldn't be processed during delta coalescing
        # (since asyncio.Queue doesn't support push_front)
        pending = self.pending
        next_recovery = 0.0

        while True:
            try:
                await self.bus.admission.wait_until_open()
                if time.monotonic() >= next_recovery:
                    next_recovery = time.monotonic() + RETRY_SECONDS
                    try:
                        await self.recover()
                    except Exception:
                        logger.exception(
                            "Scheduled delivery recovery failed; check the instance delivery store"
                        )
                # First check pending buffer before waiting on queue
                if pending:
                    msg = pending.pop(0)
                else:
                    # wait_for creates a child task: it can remove the last
                    # queued message before this dispatcher records ownership.
                    # Keep dequeue and the busy claim in the same task.
                    async with asyncio.timeout(1.0):
                        msg = await self.bus.consume_outbound()
                self.dispatching = True
                # Intake can close while an empty queue is awaited. Retain the
                # message, but do not start another transport write while paused.
                await self.bus.admission.wait_until_open()

                await self.notifications.record(msg)
                event = msg.event
                progress_event = event if isinstance(event, ProgressEvent) else None
                if progress_event and (
                    progress_event.reasoning_delta
                    or progress_event.reasoning_end
                    or progress_event.reasoning
                ):
                    # Reasoning rides its own plugin channel: only delivered
                    # when the destination channel opts in via ``show_reasoning``
                    # and overrides the streaming primitives. Channels without
                    # a low-emphasis UI affordance keep the base no-op and the
                    # content silently drops here.
                    channel = self.channel(msg.channel)
                    if channel is not None and channel.show_reasoning:
                        await self.delivery.queue(channel, msg)
                    continue

                if progress_event:
                    if progress_event.tool_hint and not self.sends_progress(
                        msg.channel,
                        tool_hint=True,
                    ):
                        continue
                    if not progress_event.tool_hint and not self.sends_progress(
                        msg.channel,
                        tool_hint=False,
                    ):
                        continue

                if isinstance(event, RetryWaitEvent):
                    continue

                if (
                    isinstance(event, RuntimeModelUpdatedEvent)
                    and msg.channel == "websocket"
                    and self.channel("websocket") is None
                ):
                    continue

                # Coalesce consecutive stream delta messages for the same (channel, chat_id)
                # to reduce API calls and improve streaming latency
                if isinstance(event, StreamDeltaEvent):
                    msg, extra_pending = coalesce_stream_deltas(self.bus.outbound, msg)
                    pending.extend(extra_pending)
                    event = msg.event

                channel = self.channel(msg.channel)
                if channel:
                    # Duplicate suppression is scoped to a known source message
                    # so repeated content from separate turns is still delivered.
                    if not isinstance(
                        event,
                        StreamDeltaEvent | StreamEndEvent | StreamedResponseEvent,
                    ):
                        if msg.delivery_id is None and self.origins.matches(msg):
                            logger.info(
                                "Suppressing duplicate outbound message to {}:{}",
                                msg.channel,
                                msg.chat_id,
                            )
                            continue
                    await self.delivery.queue(channel, msg)
                else:
                    logger.warning("Unknown channel: {}", msg.channel)
                    if msg.delivery_id is not None:
                        await self.delivery.durable.finish(msg, "failed", "channel_disabled")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            finally:
                self.dispatching = False
