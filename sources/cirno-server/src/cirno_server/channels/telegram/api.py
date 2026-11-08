"""Shared Telegram API retries and HTML/plain message submission."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar

from cirno_server.channels.telegram.formatting import (
    markdown_to_telegram_html,
    strip_md_block,
    tool_hint_to_telegram_blockquote,
)
from telegram import (
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
)
from telegram.error import BadRequest, RetryAfter, TimedOut

if TYPE_CHECKING:
    from loguru import Logger
from .connection import TelegramConnection

_T = TypeVar("_T")
_SEND_MAX_RETRIES = 3
_SEND_RETRY_BASE_DELAY = 0.5


@dataclass
class TelegramAPI:
    connection: TelegramConnection
    logger: Logger

    async def call_with_retry(
        self,
        fn: Callable[..., Awaitable[_T]],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """Retry new submissions only after a definitive rate-limit rejection."""
        return await self._call(False, fn, *args, **kwargs)

    async def call_idempotent(
        self,
        fn: Callable[..., Awaitable[_T]],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """Edits and named drafts can also be retried after an ambiguous timeout."""
        return await self._call(True, fn, *args, **kwargs)

    async def _call(
        self,
        idempotent: bool,
        fn: Callable[..., Awaitable[_T]],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        for attempt in range(1, _SEND_MAX_RETRIES + 1):
            try:
                return await fn(*args, **kwargs)
            except TimedOut:
                if not idempotent or attempt == _SEND_MAX_RETRIES:
                    raise
                delay = _SEND_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                self.logger.warning(
                    "timeout (attempt {}/{}), retrying in {:.1f}s",
                    attempt,
                    _SEND_MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
            except RetryAfter as e:
                if attempt == _SEND_MAX_RETRIES:
                    raise
                retry_after = e.retry_after
                delay = (
                    retry_after.total_seconds()
                    if isinstance(retry_after, timedelta)
                    else float(retry_after)
                )
                self.logger.warning(
                    "Flood Control (attempt {}/{}), retrying in {:.1f}s",
                    attempt,
                    _SEND_MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("Telegram retry loop exited unexpectedly")

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_params: ReplyParameters | None = None,
        thread_kwargs: dict[str, int] | None = None,
        render_as_blockquote: bool = False,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        """Send a plain text message with HTML fallback."""
        html = (
            tool_hint_to_telegram_blockquote(text)
            if render_as_blockquote
            else markdown_to_telegram_html(text)
        )
        return await self.send_formatted(
            chat_id,
            text,
            html,
            reply_parameters=reply_params,
            reply_markup=reply_markup,
            **(thread_kwargs or {}),
        )

    async def send_formatted(
        self,
        chat_id: int,
        markdown: str,
        html: str,
        **kwargs: Any,
    ) -> Message:
        """Send one rendered chunk; only a definitive rejection permits plain fallback."""
        app = self.connection.require_app()
        try:
            return await self.call_with_retry(
                app.bot.send_message,
                chat_id=chat_id,
                text=html,
                parse_mode="HTML",
                **kwargs,
            )
        except BadRequest as e:
            self.logger.warning("HTML parse failed, falling back to plain text: {}", e)
            return await self.call_with_retry(
                app.bot.send_message,
                chat_id=chat_id,
                text=markdown,
                **kwargs,
            )

    async def send_preview(self, chat_id: int, markdown: str, **kwargs: Any) -> Message:
        """A live legacy tail is plain text until its final formatting pass."""
        return await self.call_with_retry(
            self.connection.require_app().bot.send_message,
            chat_id=chat_id,
            text=strip_md_block(markdown),
            **kwargs,
        )

    @staticmethod
    def is_not_modified_error(exc: Exception) -> bool:
        return isinstance(exc, BadRequest) and "message is not modified" in str(exc).lower()

    async def edit_formatted(
        self,
        chat_id: int,
        message_id: int,
        markdown: str,
        html: str,
    ) -> None:
        """Update one existing chunk, including an already-applied edit."""
        app = self.connection.require_app()
        try:
            await self.call_idempotent(
                app.bot.edit_message_text,
                chat_id=chat_id,
                message_id=message_id,
                text=html,
                parse_mode="HTML",
            )
        except BadRequest as exc:
            if self.is_not_modified_error(exc):
                return
            self.logger.debug("HTML edit rejected, trying plain text: {}", exc)
            try:
                await self.call_idempotent(
                    app.bot.edit_message_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=markdown,
                )
            except BadRequest as plain_error:
                if not self.is_not_modified_error(plain_error):
                    raise
