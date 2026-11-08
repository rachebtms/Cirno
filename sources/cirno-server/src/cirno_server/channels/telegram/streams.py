"""Admit deltas and update one Telegram preview per chat."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from cirno_core.bus.delivery import ChannelNotReadyError
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.channels.telegram.formatting import (
    strip_md_block,
)
from cirno_server.channels.telegram.state import (
    StreamBuf,
)

from . import limits
from .api import TelegramAPI
from .destination import personal_chat_id
from .finalizer import TelegramStreamFinalizer
from .overflow import TelegramStreamOverflow
from .presence import TelegramPresence
from .rich import TelegramRichMessages
from .writer import TelegramStreamWriter


@dataclass
class TelegramStreams:
    api: TelegramAPI
    rich: TelegramRichMessages
    presence: TelegramPresence
    overflow: TelegramStreamOverflow
    writer: TelegramStreamWriter
    config: TelegramConfig
    buffers: dict[str, StreamBuf] = field(default_factory=dict)
    finalizer: TelegramStreamFinalizer = field(init=False)

    def __post_init__(self) -> None:
        self.finalizer = TelegramStreamFinalizer(
            self.rich, self.presence, self.writer, self.buffers
        )

    async def send_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
        stream_end: bool = False,
        resuming: bool = False,
        merge_next: bool = False,
    ) -> None:
        """Stream a rich draft in private chats, then persist the final message."""
        meta = metadata or {}
        int_chat_id = personal_chat_id(chat_id, meta)
        app = await self.api.connection.wait_for_app()
        if app is None:
            raise ChannelNotReadyError("Telegram bot not running")

        if stream_end and merge_next:
            if not delta:
                return
            stream_end = False
        if stream_end:
            buf = self.buffers.get(chat_id)
            if buf is None:
                return
            if stream_id is not None and buf.stream_id is not None and buf.stream_id != stream_id:
                return
            buf.require_deliverable()
            if not buf.text or (buf.message_id is None and buf.draft_id is None):
                return
            await self.finalizer.finish(chat_id, buf, meta)
            return

        buf = self.buffers.get(chat_id)
        if buf is None or (
            stream_id is not None and buf.stream_id is not None and buf.stream_id != stream_id
        ):
            buf = StreamBuf(stream_id=stream_id)
            self.buffers[chat_id] = buf
        elif buf.stream_id is None:
            buf.stream_id = stream_id
        buf.require_deliverable()
        buf.text += delta

        if not buf.text.strip():
            return

        now = time.monotonic()
        stream_thread_kwargs: dict[str, int] = {}
        if message_thread_id := meta.get("message_thread_id"):
            stream_thread_kwargs["message_thread_id"] = message_thread_id
        rich_draft_allowed = self.rich.rich_streaming_enabled()
        if buf.message_id is None and buf.draft_id is None:
            try:
                if rich_draft_allowed and len(buf.text) <= limits.TELEGRAM_RICH_MAX_LEN:
                    buf.draft_id = self.rich.new_rich_draft_id()
                    if not await self.rich.try_send_rich_draft(
                        int_chat_id,
                        buf.draft_id,
                        buf.text,
                        stream_thread_kwargs,
                    ):
                        buf.draft_id = None
                if buf.draft_id is None:
                    await self.writer.write_legacy(
                        int_chat_id,
                        buf,
                        stream_thread_kwargs,
                        preview_tail=True,
                    )
                buf.last_edit = now
            except Exception as e:
                self.api.logger.warning("Stream initial send failed: {}", e)
                raise
        else:
            edit_interval = (
                max(self.config.stream_edit_interval, limits.TELEGRAM_RICH_DRAFT_MIN_INTERVAL)
                if buf.draft_id is not None
                else self.config.stream_edit_interval
            )
            if (now - buf.last_edit) < edit_interval:
                return
            overflow_limit = (
                limits.TELEGRAM_RICH_MAX_LEN
                if buf.draft_id is not None
                else limits.TELEGRAM_MAX_MESSAGE_LEN
            )
            if len(buf.text) > overflow_limit:
                await self.overflow.flush_stream_overflow(
                    int_chat_id,
                    buf,
                    stream_thread_kwargs,
                )
                buf.last_edit = now
                return
            try:
                if buf.draft_id is not None:
                    if await self.rich.try_send_rich_draft(
                        int_chat_id,
                        buf.draft_id,
                        buf.text,
                        stream_thread_kwargs,
                    ):
                        buf.last_edit = now
                        return
                    await self.writer.write_legacy(
                        int_chat_id,
                        buf,
                        stream_thread_kwargs,
                        preview_tail=True,
                    )
                    buf.last_edit = now
                    return
                preview = strip_md_block(buf.text)
                await self.api.call_idempotent(
                    app.bot.edit_message_text,
                    chat_id=int_chat_id,
                    message_id=buf.message_id,
                    text=preview,
                )
                buf.last_edit = now
            except Exception as e:
                if self.api.is_not_modified_error(e):
                    buf.last_edit = now
                    return
                self.api.logger.warning("Stream edit failed: {}", e)
                raise
