"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from cirno_core.bus.delivery import ChannelNotReadyError
from cirno_core.bus.events import INBOUND_META_LOCAL_MEDIA, INBOUND_META_TURN_ID, OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.command.builtin.catalog import build_help_text
from cirno_core.config.network import NetworkConfig
from cirno_core.config.paths import get_media_dir
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.utils.logging_bridge import redirect_lib_logging
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.telegram.binding import TelegramBinding
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.channels.telegram.limits import (
    TELEGRAM_REPLY_CONTEXT_MAX_LEN,
)
from cirno_server.channels.telegram.liveness import _LivenessTrackedRequest
from cirno_server.channels.telegram.state import (
    QueuedTelegramUpdate,
)
from telegram import (
    BotCommand,
    Message,
    Update,
    User,
)
from telegram.error import InvalidToken, NetworkError, TimedOut
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

# A healthy getUpdates long poll completes every ~10s even with no traffic;
# PTB retries timeouts silently, so stalls must be detected here.
POLL_STALE_SECONDS = 120.0
POLL_WATCH_INTERVAL = 1.0
RESTART_BACKOFF_INITIAL_SECONDS = 5.0
RESTART_BACKOFF_MAX_SECONDS = 300.0


from cirno_server.channels.telegram.commands import (
    _TELEGRAM_COMMAND_ALIASES,
    telegram_command_text,
)

from .api import TelegramAPI
from .connection import TelegramConnection
from .delivery import TelegramDelivery
from .overflow import TelegramStreamOverflow
from .presence import TelegramPresence
from .rich import TelegramRichMessages
from .streams import TelegramStreams
from .writer import TelegramStreamWriter


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling or webhook mode.

    Long polling is the default. Webhook mode requires a public HTTPS URL and a
    Telegram secret token.
    """

    name = "telegram"
    display_name = "Telegram"
    uses_shared_proxy = True

    # Commands registered with Telegram's command menu
    BOT_COMMANDS: list[BotCommand] = [
        BotCommand("start", "Start the bot"),
        BotCommand("new", "Start a new conversation"),
        BotCommand("compact", "Compact this chat's context"),
        BotCommand("stop", "Stop the current task"),
        BotCommand("restart", "Restart the bot"),
        BotCommand("status", "Show bot status"),
        BotCommand("history", "Show recent conversation messages"),
        BotCommand("goal", "Start a sustained objective (long-running task)"),
        BotCommand("trigger", "Create a named local trigger"),
        BotCommand("model", "Switch runtime model preset"),
        BotCommand("skill", "List enabled skills"),
        BotCommand("dream", "Run Dream memory consolidation now"),
        BotCommand("dream_log", "Show the latest Dream memory change"),
        BotCommand("dream_restore", "Restore Dream memory to an earlier version"),
        BotCommand("dream_prompt", "Tell Dream how to organize memory"),
        BotCommand("help", "Show available commands"),
    ]

    # Regex for slash commands routed to AgentLoop via ``_forward_command``.
    # Telegram-safe aliases are normalized before reaching the core router.
    # Canonical hyphenated commands stay on a separate handler (below).
    TELEGRAM_BUS_SLASH_COMMAND_RE = re.compile(
        r"^/(?:new|compact|stop|restart|status|dream|history|goal|trigger|model|skill"
        r"|dream_log|dream_restore|dream_prompt)(?:@\w+)?(?:\s+[\s\S]*)?$"
    )

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return TelegramConfig().model_dump(by_alias=True)

    def __init__(
        self,
        config: Any,
        bus: MessageBus,
        *,
        network: NetworkConfig | None = None,
    ):
        if isinstance(config, dict):
            config = TelegramConfig.model_validate(config)
        super().__init__(config, bus, network=network)
        self.config: TelegramConfig = config
        self._proxy = self.network.resolve_proxy(self.config.use_proxy)
        self._media_group_buffers: dict[str, dict[str, Any]] = {}
        self._media_group_tasks: dict[str, asyncio.Task[None]] = {}
        self._bot_user_id: int | None = None
        self._bot_username: str | None = None
        self._inbound_buffers: dict[str, list[QueuedTelegramUpdate]] = {}
        self._inbound_workers: dict[str, asyncio.Task[None]] = {}
        self._last_poll_ok: float = 0.0  # monotonic time of last getUpdates round trip
        self.connection = TelegramConnection()
        self.api = TelegramAPI(self.connection, self.logger)
        self.rich = TelegramRichMessages(self.api, self.config)
        self.presence = TelegramPresence(self.connection, self.logger)
        self.writer = TelegramStreamWriter(self.api, self.rich)
        self.overflow = TelegramStreamOverflow(self.rich, self.writer)
        self.delivery = TelegramDelivery(
            self.api, self.rich, self.presence, self.config, lambda: self.show_compaction_notices
        )
        self.streams = TelegramStreams(
            self.api, self.rich, self.presence, self.overflow, self.writer, self.config
        )
        self._teardown_lock = asyncio.Lock()

    def is_allowed(self, sender_id: str) -> bool:
        """Admit only the personal account verified by the Web UI PIN."""
        binding = TelegramBinding().status()
        return bool(
            binding["bound"]
            and binding["enabled"]
            and str(sender_id).split("|", 1)[0] == binding["user_id"]
        )

    @staticmethod
    def _normalize_telegram_command(content: str) -> str:
        """Map Telegram-safe command aliases back to canonical cirno commands."""
        if not content.startswith("/"):
            return content
        command = content.split(maxsplit=1)[0]
        canonical = _TELEGRAM_COMMAND_ALIASES.get(command, command)
        return canonical + content[len(command) :]

    async def start(self) -> None:
        """Start the Telegram bot, rebuilding the app whenever polling stalls."""
        if not self.config.token:
            self.logger.error("bot token not configured")
            return

        redirect_lib_logging("telegram")
        redirect_lib_logging("httpx", level="WARNING")

        self.connection.running = True
        backoff = RESTART_BACKOFF_INITIAL_SECONDS
        while self.connection.running:
            try:
                await self._start_app()
            except InvalidToken:
                # A config error, not a blip: fail the channel. The scrubbed
                # re-raise keeps PTB's token-bearing message out of the log.
                await self._teardown_app()
                self.connection.running = False
                self.logger.error("bot token rejected by Telegram")
                raise RuntimeError("Telegram bot token was rejected by the server") from None
            except Exception as e:
                await self._teardown_app()
                if not self.connection.running:
                    break
                if not self._is_transient_startup_error(e):
                    # Never heals on its own: fail instead of retrying forever
                    # while ChannelManager keeps reporting the channel running.
                    self.connection.running = False
                    self.logger.error("startup failed: {}", self._format_telegram_error(e))
                    raise
                self.logger.error(
                    "startup failed: {}; retrying in {:.0f}s",
                    self._format_telegram_error(e),
                    backoff,
                )
                await self._idle(backoff)
                backoff = min(backoff * 2, RESTART_BACKOFF_MAX_SECONDS)
                continue

            backoff = RESTART_BACKOFF_INITIAL_SECONDS
            if not self.connection.running:
                # stop() ran while _start_app() was mid-flight and tore down the
                # previous (possibly None) app; this one would leak otherwise.
                await self._teardown_app()
                break
            stalled = await self._watch_polling()
            if not stalled or not self.connection.running:
                break
            self.logger.warning(
                "polling stalled: no getUpdates round trip for {:.0f}s; "
                "rebuilding connection pools and restarting",
                time.monotonic() - self._last_poll_ok,
            )
            await self._teardown_app()

    async def _start_app(self) -> None:
        """Build, initialize and start the Telegram application."""
        proxy = self._proxy

        # Separate pools so long-polling (getUpdates) never starves outbound sends.
        api_request = HTTPXRequest(
            connection_pool_size=self.config.connection_pool_size,
            pool_timeout=self.config.pool_timeout,
            connect_timeout=30.0,
            read_timeout=30.0,
            proxy=proxy,
        )
        poll_request = HTTPXRequest(
            connection_pool_size=4,
            pool_timeout=self.config.pool_timeout,
            connect_timeout=30.0,
            read_timeout=30.0,
            proxy=proxy,
        )
        builder = (
            Application.builder()
            .token(self.config.token)
            .request(api_request)
            .get_updates_request(_LivenessTrackedRequest(poll_request, self._note_poll_ok))
        )
        self.connection.app = builder.build()
        self.connection.app.add_error_handler(self._on_error)

        # Add command handlers (using Regex to support @username suffixes before bot initialization)
        self.connection.app.add_handler(
            MessageHandler(filters.Regex(r"^/start(?:@\w+)?$"), self._on_start)
        )
        self.connection.app.add_handler(
            MessageHandler(
                filters.Regex(TelegramChannel.TELEGRAM_BUS_SLASH_COMMAND_RE),
                self._forward_command,
            )
        )
        self.connection.app.add_handler(
            MessageHandler(
                filters.Regex(
                    r"^/(?:dream-log|dream-restore|dream-prompt)(?:@\w+)?(?:\s+[\s\S]*)?$"
                ),
                self._forward_command,
            )
        )
        self.connection.app.add_handler(
            MessageHandler(filters.Regex(r"^/help(?:@\w+)?$"), self._on_help)
        )

        # Add message handler for text, photos, video, voice, documents, and locations
        self.connection.app.add_handler(
            MessageHandler(
                (
                    filters.TEXT
                    | filters.PHOTO
                    | filters.VIDEO
                    | filters.VIDEO_NOTE
                    | filters.ANIMATION
                    | filters.VOICE
                    | filters.AUDIO
                    | filters.Document.ALL
                    | filters.LOCATION
                )
                & ~filters.COMMAND,
                self._on_message,
            )
        )

        # Conditionally register inline keyboard callback handler
        if self.config.inline_keyboards:
            self.connection.app.add_handler(CallbackQueryHandler(self._on_callback_query))
            allowed_updates = ["message", "callback_query"]
            self.logger.debug("inline keyboards enabled")
        else:
            allowed_updates = ["message"]

        if self.config.mode == "webhook":
            self.logger.info("Starting bot (webhook mode)...")
        else:
            self.logger.info("Starting bot (polling mode)...")

        # Initialize and start receiving updates
        await self.connection.app.initialize()
        await self.connection.app.start()

        # Get bot info and register command menu
        bot_info = await self.connection.app.bot.get_me()
        self._bot_user_id = getattr(bot_info, "id", None)
        self._bot_username = getattr(bot_info, "username", None)
        self.logger.info("bot @{} connected", bot_info.username)

        try:
            await self.connection.app.bot.set_my_commands(self.BOT_COMMANDS)
            self.logger.debug("bot commands registered")
        except Exception as e:
            self.logger.warning("Failed to register bot commands: {}", e)

        if self.config.mode == "webhook":
            # ``url_path`` is the local HTTP route. ``webhook_url`` is the
            # public HTTPS URL Telegram calls; reverse proxies may rewrite it.
            await cast(Any, self.connection.app.updater).start_webhook(
                listen=self.config.webhook_listen_host,
                port=self.config.webhook_listen_port,
                url_path=self.config.webhook_path.lstrip("/"),
                webhook_url=self.config.webhook_url.strip(),
                allowed_updates=allowed_updates,
                drop_pending_updates=False,
                secret_token=self.config.webhook_secret_token.strip(),
                max_connections=self.config.webhook_max_connections,
            )
        else:
            self._last_poll_ok = time.monotonic()
            await cast(Any, self.connection.app.updater).start_polling(
                allowed_updates=allowed_updates,
                drop_pending_updates=False,  # Process pending messages on startup
                error_callback=self._on_polling_error,
            )

        self.connection.ready.set()

    @staticmethod
    def _is_transient_startup_error(exc: Exception) -> bool:
        """Report whether a startup failure is worth retrying.

        HTTPXRequest wraps every httpx failure into NetworkError/TimedOut, so
        anything else is terminal: a bad proxy raises ValueError, an already
        bound webhook port raises OSError.
        """
        return isinstance(exc, NetworkError | TimedOut | asyncio.TimeoutError)

    def _note_poll_ok(self) -> None:
        # HTTP error statuses count too: the watchdog detects transport stalls,
        # not logical failures.
        self._last_poll_ok = time.monotonic()

    async def _watch_polling(self) -> bool:
        """Idle until stop(); in polling mode, return True when getUpdates goes stale."""
        watch = self.config.mode != "webhook"
        while self.connection.running:
            await asyncio.sleep(POLL_WATCH_INTERVAL)
            if watch and time.monotonic() - self._last_poll_ok > POLL_STALE_SECONDS:
                return True
        return False

    async def _idle(self, seconds: float) -> None:
        """Sleep in short steps so stop() stays responsive."""
        deadline = time.monotonic() + seconds
        while self.connection.running and time.monotonic() < deadline:
            await asyncio.sleep(POLL_WATCH_INTERVAL)

    async def _teardown_app(self) -> None:
        """Shut down the application, tolerating partially started state."""
        async with self._teardown_lock:
            app, self.connection.app = self.connection.app, None
            self.connection.ready.clear()
            if not app:
                return
            for step in (cast(Any, app.updater).stop, app.stop, app.shutdown):
                try:
                    await step()
                except Exception as e:
                    self.logger.debug("teardown step failed: {}", e)
            # Application.shutdown() skips the HTTPX pools unless initialize()
            # finished, so a failed startup leaks one per retry. This is idempotent.
            try:
                await app.bot.shutdown()
            except Exception as e:
                self.logger.debug("bot shutdown failed: {}", e)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self.connection.running = False

        tasks = {
            *self._media_group_tasks.values(),
            *self._inbound_workers.values(),
        }
        for task in tasks:
            task.cancel()
        self._media_group_tasks.clear()
        self._media_group_buffers.clear()
        self._inbound_workers.clear()
        self._inbound_buffers.clear()
        if tasks:
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    self.logger.warning("worker cleanup failed ({})", type(outcome).__name__)
        await self.presence.stop()
        self.streams.buffers.clear()
        self.delivery.compaction.messages.clear()

        if self.connection.app:
            self.logger.info("Stopping bot...")
        # Join an in-flight supervisor teardown before ChannelManager cancels
        # start(), otherwise cancellation can strand the old HTTPX pools.
        await self._teardown_app()

    def should_retry_send_error(self, error: Exception) -> bool:
        # Per-part API retries belong to this adapter. Whole-message replay is safe
        # only before submission; otherwise it may duplicate a successful prefix.
        return isinstance(error, ChannelNotReadyError)

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or update.message.chat.type != "private" or not update.effective_user:
            return

        user = update.effective_user
        sender_id = self._sender_id(user)
        if await self._try_bind(message=update.message, user=user):
            return
        if not self.is_allowed(sender_id):
            await self._send_binding_instructions(update.message)
            return
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm Cirno.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands."
        )

    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command for allowed users only."""
        if not update.message or update.message.chat.type != "private" or not update.effective_user:
            return
        user = update.effective_user
        sender_id = self._sender_id(user)
        if await self._try_bind(message=update.message, user=user):
            return
        if not self.is_allowed(sender_id):
            await self._send_binding_instructions(update.message)
            return
        await update.message.reply_text(telegram_command_text(build_help_text()))

    @staticmethod
    def _sender_id(user: User) -> str:
        """Build sender_id with username for allowlist matching."""
        sid = str(user.id)
        return f"{sid}|{user.username}" if user.username else sid

    async def _try_bind(self, *, message: Message, user: User) -> bool:
        text = (message.text or "").strip()
        if not text.startswith("/bind") and TelegramBinding().status()["bound"]:
            return False
        match = re.fullmatch(r"(?:/bind(?:@\w+)?\s+)?(\d{8})", text)
        if match is None:
            if text.startswith("/bind"):
                await message.reply_text(
                    "Send /bind followed by the eight-digit PIN from Cirno Settings → Telegram."
                )
                return True
            return False
        verified = TelegramBinding().verify(
            match[1],
            user_id=user.id,
            chat_id=message.chat_id,
            username=user.username or "",
            language=getattr(user, "language_code", None) or "en",
        )
        if verified:
            from cirno_core.notifications.inbox import NotificationInbox

            NotificationInbox().queue_pending_actions()
        await message.reply_text(
            "Connected to your Router."
            if verified
            else "Invalid or expired PIN. Generate a new PIN in Cirno Settings → Telegram."
        )
        return True

    async def _send_binding_instructions(self, message: Message) -> None:
        if message.chat.type == "private":
            await message.reply_text(
                "This is a personal Router bot. Get a PIN from Cirno Settings → Telegram, then send /bind PIN here."
            )

    @staticmethod
    def _build_message_metadata(message: Message, user: User) -> dict[str, Any]:
        """Build common Telegram inbound metadata payload."""
        reply_to = getattr(message, "reply_to_message", None)
        return {
            INBOUND_META_TURN_ID: f"telegram:{uuid4().hex}",
            "message_id": message.message_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "is_group": False,
            "reply_to_message_id": getattr(reply_to, "message_id", None) if reply_to else None,
        }

    async def _extract_reply_context(self, message: Message) -> str | None:
        """Extract text from the message being replied to, if any."""
        reply = getattr(message, "reply_to_message", None)
        if not reply:
            return None
        text = getattr(reply, "text", None) or getattr(reply, "caption", None) or ""
        if len(text) > TELEGRAM_REPLY_CONTEXT_MAX_LEN:
            text = text[:TELEGRAM_REPLY_CONTEXT_MAX_LEN] + "..."

        if not text:
            return None

        bot_id, _ = await self._ensure_bot_identity()
        reply_user = getattr(reply, "from_user", None)

        if bot_id and reply_user and getattr(reply_user, "id", None) == bot_id:
            return f"[Reply to bot: {text}]"
        elif reply_user and getattr(reply_user, "username", None):
            return f"[Reply to @{reply_user.username}: {text}]"
        elif reply_user and getattr(reply_user, "first_name", None):
            return f"[Reply to {reply_user.first_name}: {text}]"
        else:
            return f"[Reply to: {text}]"

    async def _download_message_media(
        self, msg: Message, *, add_failure_content: bool = False
    ) -> tuple[list[str], list[str]]:
        """Download media from a message (current or reply). Returns (media_paths, content_parts)."""
        media_file = None
        media_type = None
        if getattr(msg, "photo", None):
            media_file = msg.photo[-1]
            media_type = "image"
        elif getattr(msg, "voice", None):
            media_file = msg.voice
            media_type = "voice"
        elif getattr(msg, "audio", None):
            media_file = msg.audio
            media_type = "audio"
        elif getattr(msg, "document", None):
            media_file = msg.document
            media_type = "file"
        elif getattr(msg, "video", None):
            media_file = msg.video
            media_type = "video"
        elif getattr(msg, "video_note", None):
            media_file = msg.video_note
            media_type = "video"
        elif getattr(msg, "animation", None):
            media_file = msg.animation
            media_type = "animation"
        if not media_file or not self.connection.app:
            return [], []
        try:
            file = await self.connection.app.bot.get_file(media_file.file_id)
            ext = self._get_extension(
                cast(str, media_type),
                getattr(media_file, "mime_type", None),
                getattr(media_file, "file_name", None),
            )
            media_dir = get_media_dir("telegram")
            unique_id = getattr(media_file, "file_unique_id", media_file.file_id)
            file_path = media_dir / f"{unique_id}{ext}"
            await file.download_to_drive(str(file_path))
            path_str = str(file_path)
            if media_type in ("voice", "audio"):
                return [path_str], [f"[{media_type}: {path_str}]"]
            return [path_str], [f"[{media_type}: {path_str}]"]
        except Exception as e:
            self.logger.warning("Failed to download message media: {}", e)
            if add_failure_content:
                return [], [f"[{media_type}: download failed]"]
            return [], []

    async def _ensure_bot_identity(self) -> tuple[int | None, str | None]:
        """Load bot identity once and reuse it for mention/reply checks."""
        if self._bot_user_id is not None or self._bot_username is not None:
            return self._bot_user_id, self._bot_username
        if not self.connection.app:
            return None, None
        bot_info = await self.connection.app.bot.get_me()
        self._bot_user_id = getattr(bot_info, "id", None)
        self._bot_username = getattr(bot_info, "username", None)
        return self._bot_user_id, self._bot_username

    @staticmethod
    def _queue_key_for_message(message: Message) -> str:
        """Order the owner's private messages before forwarding to the Router."""
        return f"telegram:{message.chat_id}"

    @staticmethod
    def _sort_key_for_update(update: Update) -> tuple[int, int]:
        """Sort by chat message id first, then Telegram update id."""
        message = getattr(update, "message", None)
        message_id = int(getattr(message, "message_id", 0) or 0)
        update_id = int(getattr(update, "update_id", 0) or 0)
        return (message_id, update_id)

    def _enqueue_ordered_update(
        self,
        *,
        kind: Literal["command", "message"],
        update: Update,
    ) -> None:
        """Stage a Telegram update behind a short per-session reorder window."""
        message = update.message
        if message is None:
            return
        key = self._queue_key_for_message(message)
        self._inbound_buffers.setdefault(key, []).append(
            QueuedTelegramUpdate(
                kind=kind,
                update=update,
                sort_key=self._sort_key_for_update(update),
            )
        )
        if key not in self._inbound_workers:
            self._inbound_workers[key] = asyncio.create_task(self._drain_ordered_updates(key))

    async def _drain_ordered_updates(self, key: str) -> None:
        """Drain one Telegram session buffer in stable message order."""
        try:
            while self.connection.running:
                await asyncio.sleep(0.2)
                batch = self._inbound_buffers.get(key, [])
                if not batch:
                    break
                self._inbound_buffers[key] = []
                batch.sort(key=lambda item: item.sort_key)
                for item in batch:
                    try:
                        if item.kind == "command":
                            await self._process_forward_command(item.update)
                        else:
                            await self._process_message_update(item.update)
                    except Exception as e:
                        self.logger.warning(
                            "Telegram queued update handling failed for {}: {}",
                            key,
                            e,
                        )
            if not self._inbound_buffers.get(key):
                self._inbound_buffers.pop(key, None)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.warning("Telegram ordered update worker failed for {}: {}", key, e)
        finally:
            if not self._inbound_buffers.get(key):
                self._inbound_workers.pop(key, None)

    async def _forward_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Forward slash commands to the bus for unified handling in AgentLoop."""
        if not update.message or update.message.chat.type != "private" or not update.effective_user:
            return
        if not self.connection.running:
            await self._process_forward_command(update)
            return
        self._enqueue_ordered_update(kind="command", update=update)

    async def _process_forward_command(self, update: Update) -> None:
        """Process a queued slash command."""
        message = update.message
        user = update.effective_user
        if message is None or message.chat.type != "private" or user is None:
            return
        sender_id = self._sender_id(user)
        if await self._try_bind(message=message, user=user):
            return
        if not self.is_allowed(sender_id):
            await self._send_binding_instructions(message)
            return

        # Strip @bot_username suffix if present
        content = message.text or ""
        if content.startswith("/"):
            command = content.split(maxsplit=1)[0]
            content = command.split("@", 1)[0] + content[len(command) :]
        content = self._normalize_telegram_command(content)

        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(message.chat_id),
            content=content,
            metadata=self._build_message_metadata(message, user),
            session_key=ROUTER_SESSION_KEY,
        )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or update.message.chat.type != "private" or not update.effective_user:
            return
        if not self.connection.running:
            await self._process_message_update(update)
            return
        self._enqueue_ordered_update(kind="message", update=update)

    async def _process_message_update(self, update: Update) -> None:
        """Process a queued Telegram message update."""

        message = update.message
        user = update.effective_user
        if message is None or message.chat.type != "private" or user is None:
            return
        chat_id = message.chat_id
        sender_id = self._sender_id(user)
        if await self._try_bind(message=message, user=user):
            return
        if not self.is_allowed(sender_id):
            await self._send_binding_instructions(message)
            return

        # Build content from text and/or media
        content_parts: list[str] = []
        media_paths: list[str] = []

        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)

        # Location content
        if message.location:
            lat = message.location.latitude
            lon = message.location.longitude
            content_parts.append(f"[location: {lat}, {lon}]")

        # Download current message media
        current_media_paths, current_media_parts = await self._download_message_media(
            message, add_failure_content=True
        )
        media_paths.extend(current_media_paths)
        content_parts.extend(current_media_parts)
        if current_media_paths:
            self.logger.debug("Downloaded message media to {}", current_media_paths[0])

        # Reply context: text and/or media from the replied-to message
        reply = getattr(message, "reply_to_message", None)
        if reply is not None:
            reply_ctx = await self._extract_reply_context(message)
            reply_media, reply_media_parts = await self._download_message_media(reply)
            if reply_media:
                media_paths = reply_media + media_paths
                self.logger.debug("Attached replied-to media: {}", reply_media[0])
            tag = reply_ctx or (
                f"[Reply to: {reply_media_parts[0]}]" if reply_media_parts else None
            )
            if tag:
                content_parts.insert(0, tag)
        content = "\n".join(content_parts) if content_parts else "[empty message]"

        self.logger.debug("message from {}: {}...", sender_id, content[:50])

        str_chat_id = str(chat_id)
        metadata = self._build_message_metadata(message, user)
        metadata[INBOUND_META_LOCAL_MEDIA] = media_paths
        session_key = ROUTER_SESSION_KEY

        # Telegram media groups: buffer briefly, forward as one aggregated turn.
        if media_group_id := getattr(message, "media_group_id", None):
            key = f"{str_chat_id}:{media_group_id}"
            if key not in self._media_group_buffers:
                self._media_group_buffers[key] = {
                    "sender_id": sender_id,
                    "chat_id": str_chat_id,
                    "contents": [],
                    "media": [],
                    "metadata": metadata,
                    "session_key": session_key,
                }
                self.presence.start_typing(str_chat_id)
                await self.presence.add_reaction(
                    str_chat_id, message.message_id, self.config.react_emoji
                )
            buf = self._media_group_buffers[key]
            if content and content != "[empty message]":
                buf["contents"].append(content)
            buf["media"].extend(media_paths)
            if key not in self._media_group_tasks:
                self._media_group_tasks[key] = asyncio.create_task(self._flush_media_group(key))
            return

        # Start typing indicator before processing
        self.presence.start_typing(str_chat_id)
        await self.presence.add_reaction(str_chat_id, message.message_id, self.config.react_emoji)

        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata=metadata,
            session_key=session_key,
        )

    async def _flush_media_group(self, key: str) -> None:
        """Wait briefly, then forward buffered media-group as one turn."""
        try:
            await asyncio.sleep(0.6)
            if not (buf := self._media_group_buffers.pop(key, None)):
                return
            content = "\n".join(buf["contents"]) or "[empty message]"
            await self._handle_message(
                sender_id=buf["sender_id"],
                chat_id=buf["chat_id"],
                content=content,
                media=list(dict.fromkeys(buf["media"])),
                metadata={
                    **buf["metadata"],
                    INBOUND_META_LOCAL_MEDIA: list(dict.fromkeys(buf["media"])),
                },
                session_key=buf.get("session_key"),
            )
        finally:
            self._media_group_tasks.pop(key, None)

    @staticmethod
    def _format_telegram_error(exc: Exception | None) -> str:
        """Return a short, readable error summary for logs."""
        if exc is None:
            return "None"
        text = str(exc).strip()
        if text:
            return text
        if exc.__cause__ is not None:
            cause = exc.__cause__
            cause_text = str(cause).strip()
            if cause_text:
                return f"{exc.__class__.__name__} ({cause_text})"
            return f"{exc.__class__.__name__} ({cause.__class__.__name__})"
        return exc.__class__.__name__

    def _on_polling_error(self, exc: Exception) -> None:
        """Keep long-polling network failures to a single readable line."""
        summary = self._format_telegram_error(exc)
        if isinstance(exc, (NetworkError, TimedOut)):
            self.logger.warning("polling network issue: {}", summary)
        else:
            self.logger.error("polling error: {}", summary)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log polling / handler errors instead of silently swallowing them."""
        summary = self._format_telegram_error(context.error)

        if isinstance(context.error, (NetworkError, TimedOut)):
            self.logger.warning("network issue: {}", summary)
        else:
            self.logger.error("error: {}", summary)

    def _get_extension(
        self,
        media_type: str,
        mime_type: str | None,
        filename: str | None = None,
    ) -> str:
        """Get file extension based on media type or original filename."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "audio/ogg": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "video/mp4": ".mp4",
                "video/quicktime": ".mov",
                "video/webm": ".webm",
                "video/x-matroska": ".mkv",
                "video/3gpp": ".3gp",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]

        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "video": ".mp4", "file": ""}
        if ext := type_map.get(media_type, ""):
            return ext

        if filename:
            return "".join(Path(filename).suffixes)

        return ""

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard button clicks (callback queries)."""
        if not update.callback_query or not update.effective_user:
            return
        query = update.callback_query
        user = update.effective_user
        query_message = query.message
        chat_id = query_message.chat.id if query_message else None
        sender_id = self._sender_id(user)
        if not chat_id or query_message.chat.type != "private":
            self.logger.warning("Callback query without chat_id")
            return
        if not self.is_allowed(sender_id):
            return
        button_label = query.data or ""
        await query.answer()
        if isinstance(query_message, Message):
            with suppress(Exception):
                await query_message.edit_reply_markup(reply_markup=None)
        self.logger.debug("Inline button tap from {}: {}", sender_id, button_label)
        self.presence.start_typing(str(chat_id))
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(chat_id),
            content=button_label,
            metadata={
                "callback_query_id": query.id,
                "button_label": button_label,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_callback": True,
                INBOUND_META_TURN_ID: f"telegram:{uuid4().hex}",
            },
            session_key=ROUTER_SESSION_KEY,
        )

    @property
    def is_running(self) -> bool:
        return self.connection.running

    async def send(self, msg: OutboundMessage) -> None:
        await self.delivery.send(msg)

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
        await self.streams.send_delta(
            chat_id,
            delta,
            metadata,
            stream_id=stream_id,
            stream_end=stream_end,
            resuming=resuming,
            merge_next=merge_next,
        )
