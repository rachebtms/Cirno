"""Typing and reaction tasks for the personal Telegram chat."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from telegram import (
    ReactionTypeEmoji,
)

if TYPE_CHECKING:
    from loguru import Logger
from .connection import TelegramConnection


@dataclass
class TelegramPresence:
    connection: TelegramConnection
    logger: Logger
    tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    retiring: set[asyncio.Task[None]] = field(default_factory=set)

    def start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self.stop_typing(chat_id)
        self.tasks[chat_id] = asyncio.create_task(self.typing_loop(chat_id))

    def stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self.tasks.pop(chat_id, None)
        if task and not task.done():
            self.retiring.add(task)
            task.add_done_callback(self.retiring.discard)
            task.cancel()

    async def stop(self) -> None:
        """Drain active and replaced workers before closing their API connection."""
        tasks = {*self.tasks.values(), *self.retiring}
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.retiring.clear()
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                self.logger.warning("Typing worker cleanup failed: {}", outcome)

    async def add_reaction(self, chat_id: str, message_id: int, emoji: str) -> None:
        """Add emoji reaction to a message (best-effort, non-blocking)."""
        if not self.connection.app or not emoji:
            return
        try:
            await self.connection.app.bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
            )
        except Exception as e:
            self.logger.debug("reaction failed: {}", e)

    async def remove_reaction(self, chat_id: str, message_id: int) -> None:
        """Remove emoji reaction from a message (best-effort, non-blocking)."""
        if not self.connection.app:
            return
        try:
            await self.connection.app.bot.set_message_reaction(
                chat_id=int(chat_id),
                message_id=message_id,
                reaction=[],
            )
        except Exception as e:
            self.logger.debug("reaction removal failed: {}", e)

    async def typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            with suppress(asyncio.CancelledError):
                while self.connection.app:
                    await self.connection.app.bot.send_chat_action(
                        chat_id=int(chat_id), action="typing"
                    )
                    await asyncio.sleep(4)
        except Exception as e:
            self.logger.debug("Typing indicator stopped for {}: {}", chat_id, e)
