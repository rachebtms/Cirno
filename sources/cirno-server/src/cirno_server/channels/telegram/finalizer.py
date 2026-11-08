"""Commit the final Telegram stream tail once."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from cirno_server.channels.telegram.state import StreamBuf

from . import limits
from .formatting import split_telegram_markdown
from .presence import TelegramPresence
from .rich import TelegramRichMessages
from .writer import TelegramStreamWriter


@dataclass
class TelegramStreamFinalizer:
    rich: TelegramRichMessages
    presence: TelegramPresence
    writer: TelegramStreamWriter
    buffers: dict[str, StreamBuf]

    async def finish(self, chat_id: str, buf: StreamBuf, meta: dict[str, Any]) -> None:
        self.presence.stop_typing(chat_id)
        if reply_to_message_id := meta.get("message_id"):
            with suppress(ValueError):
                await self.presence.remove_reaction(chat_id, int(reply_to_message_id))

        thread_kwargs: dict[str, int] = {}
        if message_thread_id := meta.get("message_thread_id"):
            thread_kwargs["message_thread_id"] = message_thread_id

        if buf.draft_id is not None:
            chunks = split_telegram_markdown(buf.text, limits.TELEGRAM_RICH_MAX_LEN)
            for index, text in enumerate(chunks):
                if self.rich.rich_streaming_enabled() and await self.writer.write_rich(
                    int(chat_id),
                    buf,
                    text,
                    thread_kwargs,
                ):
                    buf.text = "\n".join(chunks[index + 1 :])
                    continue
                await self.writer.write_legacy(int(chat_id), buf, thread_kwargs)
                break
        else:
            await self.writer.write_legacy(int(chat_id), buf, thread_kwargs)
        self.buffers.pop(chat_id, None)
