"""Rich-message capability detection, drafts and final submissions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, cast

from cirno_server.channels.telegram.config import TelegramConfig
from telegram import (
    InlineKeyboardMarkup,
    ReplyParameters,
)
from telegram.error import BadRequest

from .api import TelegramAPI


@dataclass
class TelegramRichMessages:
    api: TelegramAPI
    config: TelegramConfig
    disabled: bool = False

    @staticmethod
    def is_rich_capability_error(exc: Exception) -> bool:
        """True when the Bot API does not support rich-message endpoints."""
        err = str(exc).lower()
        return (
            "method not found" in err
            or "unknown method" in err
            or ("endpoint" in err and "not found" in err)
            or "bad request: invalid parameter" in err
            or "unsupported" in err
            or "not implemented" in err
        )

    def rich_streaming_enabled(self) -> bool:
        return self.config.rich_messages and not self.disabled

    @staticmethod
    def rich_message_payload(content: str) -> dict[str, str]:
        return {"markdown": content}

    def mark_rich_unavailable(self, exc: Exception, operation: str) -> bool:
        if not self.is_rich_capability_error(exc):
            return False
        self.disabled = True
        self.api.logger.debug("{} unavailable, disabling rich messages: {}", operation, exc)
        return True

    async def try_send_rich(
        self,
        chat_id: int,
        content: str,
        reply_params: ReplyParameters | dict[str, int | bool] | None = None,
        thread_kwargs: dict[str, int] | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Attempt sendRichMessage (Bot API 10.1). Returns True on success."""
        if not self.api.connection.app:
            return False

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "rich_message": self.rich_message_payload(content),
        }
        if reply_params is not None:
            # sendRichMessage uses reply_parameters (object), not reply_to_message_id.
            if hasattr(reply_params, "message_id"):
                payload["reply_parameters"] = {
                    "message_id": cast(ReplyParameters, reply_params).message_id,
                    "allow_sending_without_reply": True,
                }
            else:
                payload["reply_parameters"] = reply_params
        if thread_kwargs:
            payload.update(
                {
                    k: v
                    for k, v in thread_kwargs.items()
                    if v is not None  # pyright: ignore[reportUnnecessaryComparison]
                }
            )
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            # A transport error can arrive after Telegram stores this message.
            # Only a definitive rejection permits a second submission.
            await self.api.call_with_retry(
                self.api.connection.app.bot.do_api_request,
                "sendRichMessage",
                api_kwargs=payload,
            )
            return True
        except BadRequest as exc:
            if not self.mark_rich_unavailable(exc, "sendRichMessage"):
                self.api.logger.debug("sendRichMessage rejected: {}", exc)
            return False

    @staticmethod
    def new_rich_draft_id() -> int:
        """Return a non-zero Bot API Integer suitable for one live draft."""
        return time.time_ns() % 2_147_483_647 or 1

    async def try_send_rich_draft(
        self,
        chat_id: int,
        draft_id: int,
        content: str,
        thread_kwargs: dict[str, int],
    ) -> bool:
        """Create or update the ephemeral rich preview for a private chat."""
        app = self.api.connection.require_app()
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "draft_id": draft_id,
            "rich_message": self.rich_message_payload(content),
            **thread_kwargs,
        }
        try:
            await self.api.call_idempotent(
                app.bot.do_api_request,
                "sendRichMessageDraft",
                api_kwargs=payload,
            )
            return True
        except BadRequest as exc:
            if not self.mark_rich_unavailable(exc, "sendRichMessageDraft"):
                self.api.logger.debug("Rich draft rejected: {}", exc)
            return False
