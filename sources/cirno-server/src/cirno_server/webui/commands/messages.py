"""Application orchestration for typed WebUI WebSocket commands."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from cirno_core.bus.events import INBOUND_META_LOCAL_MEDIA, INBOUND_META_USER_SHELL
from cirno_core.command.builtin.catalog import USER_SHELL_COMMAND, builtin_command_starts_agent_turn
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_INPUT_META,
    WEBUI_QUOTE_METADATA,
    RuntimeContextBlock,
    webui_quote_runtime_context,
)
from cirno_core.security.workspace_access import (
    WORKSPACE_SCOPE_METADATA_KEY,
    WorkspaceScopeError,
)
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.keys import session_key_for_channel
from cirno_core.session.session_identity import is_valid_webui_chat_id, webui_session_key
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY,
    WEBUI_RESTART_CONTROL_METADATA_KEY,
    WEBUI_SYSTEM_COMMAND_TURN_PREFIX,
)
from cirno_core.session.webui_turns.activity import (
    clear_websocket_turn_if_current,
    register_queued_websocket_turn_if_idle,
    websocket_turn_id,
    websocket_turn_wall_started_at,
)
from cirno_core.utils.prompt_templates import render_template
from loguru import logger
from websockets.asyncio.server import ServerConnection

from cirno_server.channels.websocket.attachment_store import AttachmentUploadError
from cirno_server.webui.cli_apps_api import normalize_cli_app_mentions
from cirno_server.webui.file_preview import WebUIFilePreviewError
from cirno_server.webui.mcp.mentions import normalize_mcp_preset_mentions
from cirno_server.webui.services import ServerServices
from cirno_server.webui.session_access import (
    SessionMention,
    WebuiSessionAccess,
    session_mentions_runtime_context,
)
from cirno_server.webui.temporary_chats import TemporaryChatError

from .contracts import WebUICommandTransport

if TYPE_CHECKING:
    from cirno_server.webui.outbound_delivery import WebUIOutboundDelivery

from .attachments import commit_message_attachments, parse_message_attachments


class WebUIMessageIntake:
    """Serialize, authorize and durably accept one user turn before acknowledging it."""

    def __init__(
        self,
        transport: WebUICommandTransport,
        services: ServerServices,
        *,
        outbound: WebUIOutboundDelivery,
        can_select_workspace: Callable[[ServerConnection], bool],
    ) -> None:
        self._transport, self._outbound, self.services = transport, outbound, services
        self._media, self._uploads, self._ingress = (
            services.media,
            services.uploads,
            services.ingress,
        )
        self._transcripts, self._workspaces = services.transcripts, services.workspaces
        self._temporary_chats = services.temporary_chats
        self._webui_connections = services.endpoint.webui_connections
        self._session_access = (
            WebuiSessionAccess(services.session_manager)
            if services.session_manager is not None
            else None
        )
        self._can_select_workspace = can_select_workspace
        self._accepted_messages: dict[tuple[str, str], float] = {}
        self._message_locks: dict[tuple[str, str], tuple[asyncio.Lock, int]] = {}

    async def broadcast_user_message(
        self,
        origin: ServerConnection,
        chat_id: str,
        text: str,
        *,
        turn_id: str | None,
        starts_turn: bool,
        media: list[dict[str, Any]],
        cli_apps: list[dict[str, Any]],
        mcp_presets: list[dict[str, Any]],
        session_mentions: list[SessionMention],
    ) -> None:
        body: dict[str, Any] = {
            "event": "user_message",
            "chat_id": chat_id,
            "text": text,
            "starts_turn": starts_turn,
        }
        if turn_id is not None:
            body["turn_id"] = turn_id
        if media:
            body["media_urls"] = media
        if cli_apps:
            body["cli_apps"] = cli_apps
        if mcp_presets:
            body["mcp_presets"] = mcp_presets
        if session_mentions:
            body["session_mentions"] = session_mentions
        active_turn_id = websocket_turn_id(chat_id)
        if active_turn_id is not None:
            body["active_turn_id"] = active_turn_id
        started_at = websocket_turn_wall_started_at(chat_id)
        if active_turn_id is not None and started_at is not None:
            body["started_at"] = started_at
        raw = json.dumps(body, ensure_ascii=False)
        for connection in self._transport.webui_subscribers(chat_id):
            if connection is not origin:
                await self._transport.webui_send_raw(connection, raw, label=" user_message ")

    async def workspace_scope_or_error(
        self,
        connection: ServerConnection,
        resolver: Callable[[], Awaitable[Any]],
        *,
        chat_id: str | None = None,
        turn_id: str | None = None,
        request_id: str | None = None,
    ) -> Any | None:
        try:
            return await resolver()
        except WorkspaceScopeError as exc:
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="workspace_scope_rejected",
                reason=exc.message,
                **({"request_id": request_id} if request_id else {}),
                **({"chat_id": chat_id} if chat_id else {}),
                **({"turn_id": turn_id} if turn_id else {}),
            )
            return None

    async def dispatch(
        self,
        connection: ServerConnection,
        client_id: str,
        envelope: dict[str, Any],
    ) -> None:
        chat_id, turn_id = envelope.get("chat_id"), envelope.get("turn_id")
        if not isinstance(chat_id, str) or not isinstance(turn_id, str) or not turn_id:
            await self._accept(connection, client_id, envelope)
            return
        key = (chat_id, turn_id)
        lock, users = self._message_locks.get(key, (asyncio.Lock(), 0))
        self._message_locks[key] = (lock, users + 1)
        try:
            async with lock:
                await self._accept(connection, client_id, envelope)
        except Exception:
            logger.exception(
                "WebUI message admission failed chat_id={} turn_id={}", chat_id, turn_id
            )
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="message_rejected",
                chat_id=chat_id,
                turn_id=turn_id,
                reason="The server could not accept this message. Your draft has been retained; retry after checking the server logs.",
            )
        finally:
            _, users = self._message_locks[key]
            if users == 1:
                del self._message_locks[key]
            else:
                self._message_locks[key] = (lock, users - 1)

    async def _accept(
        self,
        connection: ServerConnection,
        client_id: str,
        envelope: dict[str, Any],
    ) -> None:
        chat_id = envelope.get("chat_id")
        content = envelope.get("content")
        if not is_valid_webui_chat_id(chat_id):
            await self._transport.webui_send_event(connection, "error", detail="invalid chat_id")
            return
        raw_turn_id = envelope.get("turn_id")
        turn_id = raw_turn_id if isinstance(raw_turn_id, str) and raw_turn_id else None
        rejection_fields = {
            "chat_id": chat_id,
            **({"turn_id": turn_id} if turn_id else {}),
        }
        if not self._transport.is_allowed(client_id):
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="access_denied",
                **rejection_fields,
            )
            return
        if not isinstance(content, str):
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="missing content",
                **rejection_fields,
            )
            return
        message_rejection = self._ingress.validate_text(content)
        if message_rejection is not None:
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="message_rejected",
                reason=message_rejection,
                **rejection_fields,
            )
            return

        # A client may retry the same turn after an ACK was lost. Check before
        # resolving already-committed refs; never dispatch that turn twice.
        now = time.monotonic()
        self._accepted_messages = {
            key: expires for key, expires in self._accepted_messages.items() if expires > now
        }
        if turn_id and (chat_id, turn_id) in self._accepted_messages:
            await self._transport.webui_send_event(
                connection,
                "message_accepted",
                chat_id=chat_id,
                turn_id=turn_id,
                starts_turn=False,
            )
            return

        try:
            temporary_policy = self._temporary_chats.message_policy(
                connection,
                chat_id,
                content,
            )
        except TemporaryChatError as exc:
            await self._transport.webui_send_event(
                connection,
                "error",
                detail=exc.detail,
                **rejection_fields,
            )
            return

        raw_media = envelope.get("media", [])
        upload_owner = self._uploads.owner(connection) if raw_media else ""
        try:
            attachments = parse_message_attachments(
                raw_media, max_count=self._uploads.store.limits.max_count
            )
        except AttachmentUploadError as exc:
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="attachment_rejected",
                reason=str(exc),
                **rejection_fields,
            )
            return

        if not content.strip() and not attachments.order:
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="missing content",
                **rejection_fields,
            )
            return
        self._transport.webui_attach(connection, chat_id)
        if temporary_policy is None or temporary_policy.hydrate_transcript:
            await self._outbound.hydrate(chat_id)

        scope = (
            temporary_policy.workspace_scope
            if temporary_policy is not None
            else (
                await self.workspace_scope_or_error(
                    connection,
                    lambda: self._workspaces.scope_for_message(
                        envelope,
                        chat_id=chat_id,
                        chat_running=websocket_turn_wall_started_at(chat_id) is not None,
                        can_change_project=self._can_select_workspace(connection),
                    ),
                    chat_id=chat_id,
                    turn_id=turn_id,
                )
            )
        )
        if scope is None:
            return

        if not self._transport.is_allowed(client_id):
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="access_denied",
                **rejection_fields,
            )
            return

        metadata: dict[str, Any] = {"remote": getattr(connection, "remote_address", None)}
        if envelope.get("webui") is True:
            metadata["webui"] = True
            metadata.update(self._transcripts.client_turn_metadata(envelope.get("turn_id")))
        trusted_webui = metadata.get("webui") is True and connection in self._webui_connections
        # The settings Restart button uses the existing silent command protocol.
        # Its routing chat ID is not a new conversation or a workspace update.
        restart_control = (
            trusted_webui
            and turn_id is not None
            and turn_id.startswith(WEBUI_SYSTEM_COMMAND_TURN_PREFIX)
            and content.strip().lower() == "/restart"
            and not attachments.order
        )
        if restart_control:
            metadata[WEBUI_RESTART_CONTROL_METADATA_KEY] = True
        is_user_shell = (
            trusted_webui and envelope.get("user_shell") is True and content.startswith("!")
        )
        if is_user_shell:
            metadata[INBOUND_META_USER_SHELL] = True
        dispatch_content = (
            f"{USER_SHELL_COMMAND} {content[1:].lstrip()}" if is_user_shell else content
        )
        cli_apps = normalize_cli_app_mentions(envelope.get("cli_apps"))
        if cli_apps:
            metadata["cli_apps"] = cli_apps
        mcp_presets = normalize_mcp_preset_mentions(
            envelope.get("mcp_presets"),
            config_path=self.services.settings.config.path,
        )
        if mcp_presets:
            metadata["mcp_presets"] = mcp_presets
        session_mentions: list[SessionMention] = []
        if trusted_webui and self._session_access is not None:
            session_mentions = await self._session_access.normalize_mentions(
                envelope.get("session_mentions"),
                exclude_session_key=webui_session_key(chat_id),
            )
            if session_mentions:
                metadata["session_mentions"] = session_mentions
        metadata[WORKSPACE_SCOPE_METADATA_KEY] = scope.metadata()
        # Revalidate after all asynchronous scope/hydration work. Commit before
        # persisting paths, with no intervening await, so expiry cannot remove
        # files referenced by the canonical transcript.
        try:
            committed = await commit_message_attachments(
                attachments,
                scope=scope,
                store=self._uploads.store,
                owner=upload_owner,
            )
        except (ValueError, WebUIFilePreviewError) as exc:
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="attachment_rejected",
                reason=str(exc),
                **rejection_fields,
            )
            return
        media_paths, local, uploaded = committed.paths, committed.local, committed.uploaded
        if local:
            metadata[INBOUND_META_LOCAL_MEDIA] = [item["path"] for item in local]
        if temporary_policy is not None:
            self._temporary_chats.register_media(
                connection, chat_id, [str(item.path) for item in uploaded]
            )
        is_webui = metadata.get("webui") is True
        queued_owner = None
        if is_webui and not is_user_shell and builtin_command_starts_agent_turn(content):
            queued_owner = register_queued_websocket_turn_if_idle(chat_id, turn_id)
            if queued_owner is not None:
                metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] = queued_owner

        accepted = False
        admission_session_key = (
            temporary_policy.session_key
            if temporary_policy is not None
            else webui_session_key(chat_id)
        )
        execution_session_key = (
            temporary_policy.session_key
            if temporary_policy is not None
            else session_key_for_channel(
                "websocket",
                chat_id,
            )
        )
        session_generation: str | None = None
        session_created = False
        execution_generation: str | None = None
        execution_created = False
        try:
            if not restart_control:
                admission = await self.workspace_scope_or_error(
                    connection,
                    lambda: self._workspaces.persist_scope(
                        chat_id,
                        scope,
                        session_key=admission_session_key,
                        expected_generation=(
                            temporary_policy.session_generation
                            if temporary_policy is not None
                            else None
                        ),
                    ),
                    chat_id=chat_id,
                    turn_id=turn_id,
                )
                if admission is None:
                    return
                session_generation, session_created = admission
                execution_generation = session_generation
                if (
                    execution_session_key != admission_session_key
                    and self.services.session_manager is not None
                ):
                    (
                        execution_generation,
                        execution_created,
                    ) = await self.services.session_manager.state.open_with_metadata(
                        execution_session_key,
                        {},
                    )
            if session_generation is not None:
                metadata[HISTORY_GENERATION_METADATA_KEY] = session_generation
            if (
                is_webui
                and not restart_control
                and (temporary_policy is None or temporary_policy.persist_transcript)
            ):
                await self._transcripts.append_user_message(
                    chat_id,
                    content,
                    metadata=metadata,
                    media_paths=media_paths or None,
                    cli_apps=cli_apps or None,
                    mcp_presets=mcp_presets or None,
                    session_mentions=session_mentions or None,
                )
            if trusted_webui:
                context_blocks: list[RuntimeContextBlock] = []
                if not is_user_shell and envelope.get("intent") == "create_automation":
                    context_blocks.append(
                        RuntimeContextBlock(
                            source="webui_automation_creation",
                            content=render_template("agent/automation_creation.md", strip=True),
                        )
                    )
                quote = webui_quote_runtime_context(
                    {WEBUI_QUOTE_METADATA: envelope.get("quoted_context")}
                )
                if quote is not None:
                    context_blocks.append(quote)
                session_context = session_mentions_runtime_context(session_mentions)
                if session_context is not None:
                    context_blocks.append(session_context)
                if context_blocks:
                    metadata[RUNTIME_CONTEXT_INPUT_META] = context_blocks
            await self._transport.webui_dispatch_message(
                sender_id=client_id,
                chat_id=chat_id,
                content=dispatch_content,
                media=media_paths or None,
                metadata=metadata,
                session_key=(
                    execution_session_key
                    if temporary_policy is not None
                    or execution_session_key != admission_session_key
                    else None
                ),
                require_existing_session=(
                    temporary_policy.require_existing_session
                    if temporary_policy is not None
                    else False
                ),
                session_generation=execution_generation,
            )
            accepted = True
            if turn_id:
                self._accepted_messages[(chat_id, turn_id)] = time.monotonic() + 600
                if len(self._accepted_messages) > 1024:
                    del self._accepted_messages[next(iter(self._accepted_messages))]
        except BaseException:
            await self._workspaces.rollback_scope_admission(
                execution_session_key,
                execution_generation,
                created=execution_created,
            )
            await self._workspaces.rollback_scope_admission(
                admission_session_key,
                session_generation,
                created=session_created,
            )
            raise
        finally:
            if not accepted and queued_owner is not None:
                clear_websocket_turn_if_current(chat_id, queued_owner)

        media = (
            self._media.augment_transcript_user_media(
                media_paths,
                local_paths=[item["path"] for item in local],
                session_key=webui_session_key(chat_id),
            )
            if is_webui
            else []
        )
        for attachment, name in zip(media, attachments.names, strict=False):
            if name:
                attachment["name"] = name
        if is_webui and not restart_control:
            if session_created:
                await self._outbound.session_updated(chat_id, scope="metadata")
            await self.broadcast_user_message(
                connection,
                chat_id,
                content,
                turn_id=turn_id,
                starts_turn=queued_owner is not None,
                media=media,
                cli_apps=cli_apps,
                mcp_presets=mcp_presets,
                session_mentions=session_mentions,
            )
        if is_webui and turn_id:
            active_turn_id = websocket_turn_id(chat_id)
            started_at = websocket_turn_wall_started_at(chat_id)
            await self._transport.webui_send_event(
                connection,
                "message_accepted",
                chat_id=chat_id,
                turn_id=turn_id,
                starts_turn=queued_owner is not None,
                **({"media_urls": media} if media else {}),
                **({"active_turn_id": active_turn_id} if active_turn_id is not None else {}),
                **(
                    {"started_at": started_at}
                    if active_turn_id is not None and started_at is not None
                    else {}
                ),
            )
