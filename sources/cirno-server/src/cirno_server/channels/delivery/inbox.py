"""Persist user notices and forward opted-in notifications to personal Telegram."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import UserInputAccepted
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.session.manager import SessionManager
from loguru import logger

from cirno_server.channels.base import BaseChannel


class InboxDelivery:
    def __init__(
        self,
        bus: MessageBus,
        config_path: Path,
        sessions: SessionManager | None,
        channel: Callable[[str], BaseChannel | None],
    ) -> None:
        self.bus = bus
        self.config_path = config_path
        self.sessions = sessions
        self.channel = channel
        self.inbox = NotificationInbox(config_path.parent / "state")
        self._unsubscribe = bus.subscribe(self.answer, UserInputAccepted)

    def close(self) -> None:
        self._unsubscribe()

    async def record(self, msg: OutboundMessage) -> None:
        notice = self.inbox.prepare(msg)
        if notice is None:
            return
        try:
            if self.sessions is not None:
                session = await self.sessions.state.read_header(notice["session_key"])
                if session is not None:
                    if not session.policy.persist:
                        return
                    generation = msg.metadata.get("_session_generation") or msg.metadata.get(
                        "_history_generation"
                    )
                    if generation and generation != session.generation:
                        return
                    notice["data"] = {
                        **notice.get("data", {}),
                        "session_generation": session.generation,
                        "session_title": session.metadata.get("title"),
                    }
                elif msg.channel == "websocket":
                    return
            await asyncio.to_thread(self.inbox.record, **notice)
            await self.queue_telegram()
        except (OSError, ValueError, sqlite3.Error, RuntimeError):
            logger.exception(
                "Could not persist or forward Inbox notification; channel delivery continues"
            )

    async def answer(self, event: UserInputAccepted) -> None:
        if event.context.channel != "websocket" or event.context.metadata.get("_session_message"):
            return
        await asyncio.to_thread(self.inbox.answer, event.context.session_key, event.content)

    async def queue_telegram(self) -> None:
        if self.channel("telegram") is None:
            return
        from cirno_server.channels.telegram.binding import TelegramBinding
        from cirno_server.channels.telegram.notifications import notification_message

        state = await asyncio.to_thread(TelegramBinding(self.config_path.parent / "state").status)
        if not state["bound"]:
            return
        for notice in await asyncio.to_thread(self.inbox.telegram_pending, state["bound_at"]):
            should_send = (
                state["enabled"]
                and notice["category"] in state["notifications"]
                and (notice["created_at"] >= state["bound_at"] or notice["status"] == "pending")
                and (notice["category"] != "operations" or notice["status"] == "pending")
            )
            if should_send:
                # Record in the existing durable outbox before acknowledging the
                # Inbox queue. A restart cannot lose an admitted notification.
                await self.bus.publish_outbound(notification_message(notice, state))
            await asyncio.to_thread(self.inbox.telegram_queued, notice["id"], notice["revision"])
