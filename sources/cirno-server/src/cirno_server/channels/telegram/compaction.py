"""Collapse each compaction operation into one Telegram status message."""

from __future__ import annotations

from dataclasses import dataclass, field

from cirno_core.bus.agent_events import ContextCompactionEvent
from cirno_core.bus.events import OutboundMessage
from telegram import ReplyParameters
from telegram.error import BadRequest

from .api import TelegramAPI
from .limits import COMPACTION_NOTICES_MAX


@dataclass
class TelegramCompactionNotices:
    api: TelegramAPI
    messages: dict[tuple[str, str], int] = field(default_factory=dict)

    async def send(
        self,
        chat_id: int,
        msg: OutboundMessage,
        event: ContextCompactionEvent,
        reply_params: ReplyParameters | None,
        thread_kwargs: dict[str, int],
    ) -> None:
        """Deliver compaction status as one message that is edited in place.

        The started phase posts the notice and remembers its message id; a
        terminal phase rewrites that same message instead of posting another.
        If the notice cannot be edited, a fresh message keeps the outcome
        visible either way.
        """
        app = self.api.connection.require_app()
        key = (msg.chat_id, event.compaction_id)
        if event.phase == "started":
            sent = await self.api.call_with_retry(
                app.bot.send_message,
                chat_id=chat_id,
                text=msg.content,
                reply_parameters=reply_params,
                **thread_kwargs,
            )
            while len(self.messages) >= COMPACTION_NOTICES_MAX:
                self.messages.pop(next(iter(self.messages)))
            self.messages[key] = sent.message_id
            return

        message_id = self.messages.get(key)
        if message_id is None or not msg.content:
            await self.api.send_text(chat_id, msg.content, thread_kwargs=thread_kwargs)
            return
        try:
            await self.api.call_idempotent(
                app.bot.edit_message_text,
                chat_id=chat_id,
                message_id=message_id,
                text=msg.content,
            )
        except BadRequest as exc:
            if self.api.is_not_modified_error(exc):
                self.messages.pop(key, None)
                return
            self.api.logger.warning("Compaction notice edit failed, sending anew: {}", exc)
            await self.api.send_text(chat_id, msg.content, thread_kwargs=thread_kwargs)
        self.messages.pop(key, None)
