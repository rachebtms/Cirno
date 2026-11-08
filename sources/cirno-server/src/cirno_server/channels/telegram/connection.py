"""Shared application lease for inbound and outbound Telegram work."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field

from cirno_core.bus.delivery import ChannelNotReadyError
from cirno_server.channels.telegram.state import (
    TelegramApplication,
)

APP_RESTART_SEND_WAIT_SECONDS = 2.0


@dataclass
class TelegramConnection:
    app: TelegramApplication | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    running: bool = False

    def require_app(self) -> TelegramApplication:
        if self.app is None:
            raise RuntimeError("Telegram application is not started")
        return self.app

    async def wait_for_app(self) -> TelegramApplication | None:
        """Return the live app, briefly waiting out an in-flight rebuild.

        Returning quietly while ``start()`` rebuilds would let the manager count
        the message as delivered, so raise once the wait runs out. None means the
        channel is stopped: nothing left to deliver.
        """
        if self.ready.is_set() and self.app is not None:
            return self.app
        if not self.running:
            return None
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.ready.wait(), APP_RESTART_SEND_WAIT_SECONDS)
        if not self.ready.is_set() or self.app is None:
            raise ChannelNotReadyError("Telegram application is restarting; message not delivered")
        return self.app
