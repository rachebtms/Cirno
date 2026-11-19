"""Persist complete stream chunks while retaining an editable tail."""

from __future__ import annotations

from dataclasses import dataclass

from cirno_server.channels.telegram.state import StreamBuf

from . import limits
from .formatting import iter_telegram_markdown_fragments
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
            chunks = iter_telegram_markdown_fragments(
                buf.text, limits.TELEGRAM_RICH_MAX_LEN, line_continuation=buf.line_continuation,
            )
            for chunk in chunks:
                if not chunk.remainder.strip():
                    break
                if await self.writer.write_rich(chat_id, buf, chunk.markdown, thread_kwargs):
                    buf.text = chunk.remainder
                    buf.line_continuation = chunk.remainder_line_continuation
                    continue
                await self.writer.write_legacy(chat_id, buf, thread_kwargs)
                return
            buf.draft_id = self.rich.new_rich_draft_id()
            if await self.rich.try_send_rich_draft(
                chat_id, buf.draft_id, buf.text, thread_kwargs,
                **({"line_continuation": True} if buf.line_continuation else {}),
            ):
                return
        await self.writer.write_legacy(chat_id, buf, thread_kwargs)
