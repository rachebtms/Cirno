"""Personal Telegram delivery, media and inline action rendering."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import urlparse

from cirno_core.bus.agent_events import ContextCompactionEvent
from cirno_core.bus.delivery import ChannelNotReadyError
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.security.network import validate_url_target
from cirno_server.channels.telegram.commands import (
    telegram_command_text,
)
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.channels.telegram.formatting import (
    split_telegram_markdown,
)
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyParameters,
)

from . import limits
from .api import TelegramAPI
from .compaction import TelegramCompactionNotices
from .destination import personal_chat_id
from .presence import TelegramPresence
from .rich import TelegramRichMessages


@dataclass
class TelegramDelivery:
    api: TelegramAPI
    rich: TelegramRichMessages
    presence: TelegramPresence
    config: TelegramConfig
    show_compaction_notices: Callable[[], bool]
    compaction: TelegramCompactionNotices = field(init=False)

    def __post_init__(self) -> None:
        self.compaction = TelegramCompactionNotices(self.api)

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if isinstance(msg.event, ContextCompactionEvent) and not (
            msg.event.notify or self.show_compaction_notices()
        ):
            return
        chat_id = personal_chat_id(msg.chat_id, msg.metadata)
        app = await self.api.connection.wait_for_app()
        if app is None:
            raise ChannelNotReadyError("Telegram bot not running")

        progress_event = msg.event if isinstance(msg.event, ProgressEvent) else None

        # Only stop typing indicator and remove reaction for final responses
        if progress_event is None:
            self.presence.stop_typing(msg.chat_id)
            if reply_to_message_id := msg.metadata.get("message_id"):
                with suppress(ValueError):
                    await self.presence.remove_reaction(msg.chat_id, int(reply_to_message_id))

        reply_to_message_id = msg.metadata.get("message_id")
        message_thread_id = msg.metadata.get("message_thread_id")
        thread_kwargs: dict[str, int] = {}
        if message_thread_id is not None:
            thread_kwargs["message_thread_id"] = message_thread_id

        reply_params = None
        if self.config.reply_to_message:
            if reply_to_message_id:
                reply_params = ReplyParameters(
                    message_id=reply_to_message_id, allow_sending_without_reply=True
                )

        # Compaction notices collapse into one message: the started phase sends
        # it, a terminal phase edits it in place instead of posting a new one.
        if isinstance(msg.event, ContextCompactionEvent):
            await self.compaction.send(
                chat_id,
                msg,
                msg.event,
                reply_params,
                thread_kwargs,
            )
            return

        # Send media files
        for media_path in msg.media or []:
            try:
                media_type = self.get_media_type(media_path)
                sender = {
                    "photo": app.bot.send_photo,
                    "video": app.bot.send_video,
                    "voice": app.bot.send_voice,
                    "audio": app.bot.send_audio,
                }.get(media_type, app.bot.send_document)
                param = {
                    "photo": "photo",
                    "video": "video",
                    "voice": "voice",
                    "audio": "audio",
                }.get(media_type, "document")
                extra: dict[str, Any] = {}
                if media_type == "video":
                    extra["supports_streaming"] = True

                # Telegram Bot API accepts HTTP(S) URLs directly for media params.
                if self.is_remote_media_url(media_path):
                    ok, error = validate_url_target(media_path)
                    if not ok:
                        raise ValueError(f"unsafe media URL: {error}")
                    await self.api.call_with_retry(
                        sender,
                        chat_id=chat_id,
                        **{param: media_path},
                        reply_parameters=reply_params,
                        **thread_kwargs,
                        **extra,
                    )
                    continue

                media_bytes = Path(media_path).read_bytes()
                filename = Path(media_path).name
                send_kwargs = {param: media_bytes, "filename": filename}
                await self.api.call_with_retry(
                    sender,
                    chat_id=chat_id,
                    reply_parameters=reply_params,
                    **thread_kwargs,
                    **extra,
                    **send_kwargs,
                )
            except Exception:
                filename = media_path.rsplit("/", 1)[-1]
                self.api.logger.exception("Failed to send media {}", media_path)
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"[File delivery could not be confirmed: {filename}]",
                    reply_parameters=reply_params,
                    **thread_kwargs,
                )
                raise

        # Send text content
        if msg.content and msg.content != "[empty message]":
            render_as_blockquote = bool(progress_event and progress_event.tool_hint)
            buttons = cast(list[list[str]], getattr(msg, "buttons", None) or [])
            action_url = msg.metadata.get("_telegram_action_url")
            reply_markup = (
                InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                msg.metadata.get("_telegram_action_label", "Open Cirno Inbox"),
                                url=action_url,
                            )
                        ]
                    ]
                )
                if action_url
                else self.build_keyboard(buttons)
                if buttons
                else None
            )
            text = msg.content
            if msg.metadata.get("render_as") == "text":
                text = telegram_command_text(text)
            # Fallback: no native keyboard → splice labels into the message so the choices survive.
            if buttons and reply_markup is None:
                text = f"{text}\n\n{self.buttons_as_text(buttons)}"

            # Bot API 10.1 rich fast-path: send raw markdown via sendRichMessage.
            # All non-blockquote content tries rich first; _rich_send_disabled
            # latches off permanently if the server doesn't support it.
            if not render_as_blockquote and self.config.rich_messages and not self.rich.disabled:
                rich_ok = await self.rich.try_send_rich(
                    chat_id,
                    text,
                    reply_params,
                    thread_kwargs,
                    reply_markup,
                )
                if rich_ok:
                    return

            chunks = split_telegram_markdown(text, limits.TELEGRAM_MAX_MESSAGE_LEN)
            for i, chunk in enumerate(chunks):
                is_last = i == len(chunks) - 1
                await self.api.send_text(
                    chat_id,
                    chunk,
                    reply_params,
                    thread_kwargs,
                    render_as_blockquote=render_as_blockquote,
                    reply_markup=reply_markup if is_last else None,
                )

    @staticmethod
    def get_media_type(path: str) -> str:
        """Guess media type from file extension."""
        filename = urlparse(path).path if path.startswith(("http://", "https://")) else path
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp"):
            return "photo"
        if ext in ("mp4", "mov", "avi", "mkv", "webm", "3gp"):
            return "video"
        if ext == "ogg":
            return "voice"
        if ext in ("mp3", "m4a", "wav", "aac"):
            return "audio"
        return "document"

    @staticmethod
    def is_remote_media_url(path: str) -> bool:
        return path.startswith(("http://", "https://"))

    def build_keyboard(self, buttons: list[list[str]]) -> InlineKeyboardMarkup | None:
        """Build inline keyboard markup if inline_keyboards is enabled."""
        if not buttons or not self.config.inline_keyboards:
            return None
        keyboard = [
            [
                InlineKeyboardButton(label, callback_data=self.safe_callback_data(label))
                for label in row
            ]
            for row in buttons
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def safe_callback_data(label: str) -> str:
        # Telegram caps callback_data at 64 bytes UTF-8; truncate at a char boundary so the keyboard still sends.
        encoded = label.encode("utf-8")
        if len(encoded) <= 64:
            return label
        return encoded[:64].decode("utf-8", errors="ignore")

    @staticmethod
    def buttons_as_text(buttons: list[list[str]]) -> str:
        # Buttons are semantic options; when we can't render a keyboard, the user still needs to see them.
        return "\n".join(" ".join(f"[{label}]" for label in row) for row in buttons if row)
