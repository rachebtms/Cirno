"""WebUI chat fork orchestration."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from cirno_core.session.manager import SessionManager
from cirno_core.session.roles import conversation_role
from cirno_core.session.session_identity import is_valid_webui_chat_id, webui_session_key
from cirno_core.session.transcript import session_display_facts
from cirno_core.session.webui_turns.titles import clean_generated_title
from loguru import logger

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from cirno_server.webui.services import ServerServices


class WebUIForkHost(Protocol):
    gateway: ServerServices

    async def send_webui_protocol_error(
        self,
        connection: ServerConnection,
        detail: str,
        *,
        request_id: str | None = None,
    ) -> None: ...

    async def attach_webui_fork(
        self,
        connection: ServerConnection,
        *,
        fork_id: str,
        fork_key: str,
        request_id: str | None = None,
    ) -> None: ...


async def create_webui_chat_fork(
    session_manager: SessionManager,
    *,
    source_chat_id: str,
    before_user_index: int,
    title: str | None = None,
) -> tuple[str, str] | None:
    """Return ``(chat_id, session_key)`` for a new fork, or ``None`` for bad input."""
    new_id = str(uuid.uuid4())
    source_key = webui_session_key(source_chat_id)
    target_key = webui_session_key(new_id)
    forked = await session_manager.state.fork(
        source_key, target_key, before_user_index,
        title=clean_generated_title(title), history_projection=session_display_facts,
    )
    if forked is None:
        return None
    return new_id, target_key


async def handle_webui_fork_chat(
    channel: WebUIForkHost,
    connection: ServerConnection,
    envelope: Mapping[str, Any],
) -> None:
    """Handle the WebUI ``fork_chat`` websocket command.

    ``websocket.py`` owns the transport. This module owns WebUI fork semantics:
    validate the request, clone session/transcript state, attach the new chat,
    and hydrate the client.
    """
    source_chat_id = envelope.get("source_chat_id")
    request_id = envelope.get("request_id")
    correlation = {"request_id": request_id} if isinstance(request_id, str) else {}
    raw_index = envelope.get("before_user_index")
    if not is_valid_webui_chat_id(source_chat_id):
        await channel.send_webui_protocol_error(connection, "invalid source_chat_id", **correlation)
        return
    if not conversation_role(webui_session_key(source_chat_id)).can_fork:
        await channel.send_webui_protocol_error(connection, "The Router conversation cannot be forked", **correlation)
        return
    if isinstance(raw_index, bool) or not isinstance(raw_index, int) or raw_index < 0:
        await channel.send_webui_protocol_error(connection, "invalid before_user_index", **correlation)
        return

    session_manager = channel.gateway.session_manager
    if session_manager is None:
        await channel.send_webui_protocol_error(connection, "session_manager_unavailable", **correlation)
        return

    try:
        forked = await create_webui_chat_fork(
            session_manager,
            source_chat_id=source_chat_id,
            before_user_index=raw_index,
            title=envelope.get("title") if isinstance(envelope.get("title"), str) else None,
        )
        if forked is None:
            await channel.send_webui_protocol_error(connection, "invalid fork source or index", **correlation)
            return
        fork_id, fork_key = forked
    except Exception as exc:
        logger.warning("fork_chat failed: {}", exc)
        await channel.send_webui_protocol_error(connection, "fork_chat_failed", **correlation)
        return

    await channel.attach_webui_fork(
        connection,
        fork_id=fork_id,
        fork_key=fork_key,
        **correlation,
    )
