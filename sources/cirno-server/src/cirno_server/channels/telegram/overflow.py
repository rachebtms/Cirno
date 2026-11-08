"""Persist complete stream chunks while retaining an editable tail."""

from __future__ import annotations

from dataclasses import dataclass

from cirno_server.channels.telegram.state import StreamBuf

from . import limits
from .formatting import split_telegram_markdown
from .rich import TelegramRichMessages
from .writer import TelegramStreamWriter


@dataclass
class TelegramStreamOverflow:
    rich: TelegramRichMessages
    writer: TelegramStreamWriter

    async def flush_stream_overflow(
        self,
        chat_id: int,
        buf: StreamBuf,
        thread_kwargs: dict[str, int],
    ) -> None:
        """Commit full rich chunks or use the shared HTML/plain writer."""
        if buf.draft_id is not None:
            if not self.rich.rich_streaming_enabled():
                await self.writer.write_legacy(chat_id, buf, thread_kwargs)
                return
            chunks = split_telegram_markdown(buf.text, limits.TELEGRAM_RICH_MAX_LEN)
            for index, text in enumerate(chunks[:-1]):
                if await self.writer.write_rich(chat_id, buf, text, thread_kwargs):
                    buf.text = "\n".join(chunks[index + 1 :])
                    continue
                await self.writer.write_legacy(chat_id, buf, thread_kwargs)
                return
            buf.draft_id = self.rich.new_rich_draft_id()
            if await self.rich.try_send_rich_draft(chat_id, buf.draft_id, buf.text, thread_kwargs):
                return
        await self.writer.write_legacy(chat_id, buf, thread_kwargs)
