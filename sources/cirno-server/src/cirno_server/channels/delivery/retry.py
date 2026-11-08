"""Retry only when the adapter can safely repeat an outbound submission."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable

from cirno_core.bus.delivery import DeliveryRejectedError
from cirno_core.bus.events import OutboundMessage
from loguru import logger

from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.events import send_event

# Equal-jitter upper bounds: 1s, 2s, then 4s.
RETRY_DELAYS = (1, 2, 4)


class RetrySender:
    def __init__(self, slots: asyncio.Semaphore, retry_limit: Callable[[], int]) -> None:
        self.slots = slots
        self.retry_limit = retry_limit

    async def send(
        self,
        channel: BaseChannel,
        msg: OutboundMessage,
        *,
        deadline: float | None = None,
    ) -> None:
        """Send a message with retry on failure using exponential backoff.

        When deadline is provided, retry until that monotonic time instead of
        stopping at the configured attempt limit.

        Note: CancelledError is re-raised to allow graceful shutdown.
        """
        max_attempts = max(self.retry_limit(), 1)
        attempt = 0

        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    await self.slots.acquire()
            except TimeoutError:
                logger.warning("Send to {} deadline expired waiting for a send slot", msg.channel)
                return
            try:
                try:
                    if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                        logger.warning("Send to {} deadline expired before submission", msg.channel)
                        return
                    attempt += 1
                    # The deadline bounds admission, not an already-submitted send.
                    await send_event(channel, msg)
                finally:
                    self.slots.release()
                return  # Send succeeded
            except asyncio.CancelledError:
                raise  # Propagate cancellation for graceful shutdown
            except Exception as e:
                if isinstance(e, DeliveryRejectedError) or not channel.should_retry_send_error(e):
                    logger.error(
                        "Send to {} failed with a non-retryable {}: {}",
                        msg.channel,
                        type(e).__name__,
                        e,
                    )
                    return
                loop = asyncio.get_running_loop()
                exhausted = attempt >= max_attempts if deadline is None else loop.time() >= deadline
                if exhausted:
                    logger.exception(
                        "Failed to send to {} after {} attempts",
                        msg.channel,
                        attempt,
                    )
                    return
                base = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
                delay = random.uniform(base / 2, base)
                if deadline is not None:
                    delay = min(delay, max(0.0, deadline - loop.time()))
                attempt_label = str(attempt)
                if deadline is None:
                    attempt_label = f"{attempt}/{max_attempts}"
                logger.warning(
                    "Send to {} failed (attempt {}): {}, retrying in {}s",
                    msg.channel,
                    attempt_label,
                    type(e).__name__,
                    delay,
                )
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise  # Propagate cancellation during sleep
