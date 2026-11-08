"""Shared stream chunk commits, with explicit uncertain-delivery ownership."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from cirno_server.channels.telegram.state import StreamBuf
from telegram.error import BadRequest, RetryAfter

from . import limits
from .api import TelegramAPI
from .formatting import split_telegram_markdown_html_chunks
from .rich import TelegramRichMessages

_T = TypeVar("_T")


@dataclass
class TelegramStreamWriter:
    api: TelegramAPI
    rich: TelegramRichMessages

    @staticmethod
    async def submit(buf: StreamBuf, operation: Callable[[], Awaitable[_T]]) -> _T:
        """An uncertain new-message outcome cannot be replayed by a later delta."""
        buf.require_deliverable()
        try:
            return await operation()
        except (BadRequest, RetryAfter):
            # Telegram rejected the request, so no message was stored.
            raise
        except asyncio.CancelledError:
            buf.delivery_error = "message submission was interrupted"
            raise
        except Exception as exc:
            buf.delivery_error = f"{type(exc).__name__}: {exc}"
            raise

    async def write_rich(
        self,
        chat_id: int,
        buf: StreamBuf,
        text: str,
        thread_kwargs: dict[str, int],
    ) -> bool:
        return await self.submit(
            buf,
            lambda: self.rich.try_send_rich(chat_id, text, thread_kwargs=thread_kwargs),
        )

    async def write_legacy(
        self,
        chat_id: int,
        buf: StreamBuf,
        thread_kwargs: dict[str, int],
        *,
        preview_tail: bool = False,
    ) -> None:
        """Keep the last confirmed message editable and retain only its unsent tail."""
        buf.require_deliverable()
        chunks = split_telegram_markdown_html_chunks(buf.text, limits.TELEGRAM_HTML_MAX_LEN)
        first = 0
        if buf.message_id is not None:
            markdown, html = chunks[0]
            await self.api.edit_formatted(chat_id, buf.message_id, markdown, html)
            first = 1
        for index in range(first, len(chunks)):
            markdown, html = chunks[index]
            operation = (
                (lambda: self.api.send_preview(chat_id, markdown, **thread_kwargs))
                if preview_tail and index == len(chunks) - 1
                else (lambda: self.api.send_formatted(chat_id, markdown, html, **thread_kwargs))
            )
            sent = await self.submit(buf, operation)
            buf.message_id = sent.message_id
            buf.draft_id = None
            buf.text = "\n".join(markdown for markdown, _ in chunks[index:])
