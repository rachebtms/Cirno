"""Application orchestration for typed WebUI WebSocket commands."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any, cast

from cirno_core.security.workspace_access import (
    WORKSPACE_SCOPE_METADATA_KEY,
)
from cirno_core.session.session_identity import is_valid_webui_chat_id, webui_session_key
from cirno_core.session.webui_turns.activity import (
    clear_websocket_turns,
    websocket_turn_wall_started_at,
)
from websockets.asyncio.server import ServerConnection

from cirno_server.webui.forking import handle_webui_fork_chat
from cirno_server.webui.services import ServerServices
from cirno_server.webui.sidebar_state import write_webui_sidebar_state
from cirno_server.webui.temporary_chats import TemporaryChatError

from .contracts import WebUICommandTransport, is_request_id
from .messages import WebUIMessageIntake
from .requests import WebUIRequests

if TYPE_CHECKING:
    from cirno_server.webui.outbound_delivery import WebUIOutboundDelivery


class WebUICommandRouter:
    """Own WebUI command semantics while a transport host owns raw connections."""

    def __init__(
        self,
        transport: WebUICommandTransport,
        gateway: ServerServices,
        *,
        outbound: WebUIOutboundDelivery,
    ) -> None:
        self._transport = transport
        self._outbound = outbound
        self.gateway = gateway
        self._http_router = gateway.http
        self._workspaces = gateway.workspaces
        self._temporary_chats = gateway.temporary_chats
        self._session_projection = gateway.session_projection
        self._webui_connections = gateway.endpoint.webui_connections
        self.requests = WebUIRequests(
            transport,
            gateway,
            can_select_workspace=self.workspace_project_selection_available,
            broadcast=self.broadcast_webui_event,
        )
        self.messages = WebUIMessageIntake(
            transport,
            gateway,
            outbound=outbound,
            can_select_workspace=self.workspace_project_selection_available,
        )

    def workspace_project_selection_available(self, connection: ServerConnection) -> bool:
        return self._http_router.workspace_project_selection_available(connection)

    async def send_webui_protocol_error(
        self,
        connection: ServerConnection,
        detail: str,
        *,
        request_id: str | None = None,
    ) -> None:
        await self._transport.webui_send_event(
            connection, "error", detail=detail,
            **({"request_id": request_id} if request_id is not None else {}),
        )

    async def attach_webui_fork(
        self,
        connection: ServerConnection,
        *,
        fork_id: str,
        fork_key: str,
        request_id: str | None = None,
    ) -> None:
        scope = await self._workspaces.async_scope_for_session_key(fork_key)
        self._transport.webui_attach(connection, fork_id)
        await self._transport.webui_send_event(
            connection,
            "attached",
            chat_id=fork_id,
            **({"request_id": request_id} if request_id is not None else {}),
            **(await self._session_projection.attach_fields(fork_key)),
        )
        await self._transport.webui_send_event(
            connection,
            "session_updated",
            chat_id=fork_id,
            scope="metadata",
            workspace_scope=scope.payload(),
        )
        await self._outbound.hydrate(fork_id)

    async def discard_owned_chat(
        self,
        connection: ServerConnection,
        chat_id: str,
    ) -> None:
        await self._temporary_chats.discard(connection, chat_id)
        self._transport.webui_detach(connection, chat_id)
        clear_websocket_turns(chat_id)
        self._outbound.discard(chat_id)

    async def cleanup_connection(self, connection: ServerConnection) -> None:
        """Release command-owned state associated with one transport connection."""
        chat_ids = self._transport.webui_connection_chats(connection)
        for chat_id in chat_ids:
            if self._temporary_chats.owns(connection, chat_id):
                await self.discard_owned_chat(connection, chat_id)
            else:
                self._transport.webui_detach(connection, chat_id)
        for chat_id in self._temporary_chats.chat_ids_for_owner(connection):
            await self.discard_owned_chat(connection, chat_id)
        self._transport.webui_clear_connection_default(connection)
        self.gateway.endpoint.discard_connection(connection)
        self.requests.discard_connection_if_idle(connection)

    async def broadcast_webui_event(self, event: str, **fields: Any) -> None:
        for connection in tuple(self._webui_connections):
            await self._transport.webui_send_event(connection, event, **fields)

    async def dispatch(
        self,
        connection: ServerConnection,
        client_id: str,
        envelope: dict[str, Any],
    ) -> None:
        """Execute one typed WebUI command."""
        command_type = envelope.get("type")
        request_id = envelope.get("request_id")
        correlation: dict[str, Any] = {}
        if command_type in {"new_chat", "new_temporary_chat", "fork_chat"}:
            if request_id is not None and not is_request_id(request_id):
                await self.send_webui_protocol_error(connection, "invalid request_id")
                return
            if request_id is not None:
                correlation["request_id"] = request_id
        if command_type == "webui_request":
            await self.requests.start(connection, envelope)
            return
        if command_type in {"new_chat", "new_temporary_chat"} and not isinstance(
            envelope.get("ptc_mode", False), bool
        ):
            await self._transport.webui_send_event(
                connection, "error", detail="ptc_mode must be a boolean", **correlation,
            )
            return
        if command_type == "new_chat":
            project_id = envelope.get("project_id")
            new_id = str(uuid.uuid4())
            scope = await self.messages.workspace_scope_or_error(
                connection,
                lambda: self._workspaces.scope_for_new_chat(
                    envelope,
                    can_change_project=self.workspace_project_selection_available(connection),
                ),
                request_id=request_id,
            )
            if scope is None:
                return
            if project_id is not None or envelope.get("ptc_mode") is True:
                sessions = self.gateway.session_manager
                if sessions is None:
                    await self.send_webui_protocol_error(
                        connection, "Conversation storage is unavailable", **correlation,
                    )
                    return
                try:
                    await sessions.projects.open_conversation(
                        webui_session_key(new_id),
                        {
                            "webui": True,
                            "ptc_mode": envelope.get("ptc_mode", False),
                            WORKSPACE_SCOPE_METADATA_KEY: scope.payload(),
                        },
                        project_id,
                    )
                except ValueError as error:
                    await self._transport.webui_send_event(connection, "error", detail=str(error), **correlation)
                    return
            await self._workspaces.stage_scope(new_id, scope)
            self._transport.webui_attach(connection, new_id)
            await self._transport.webui_send_event(
                connection,
                "attached",
                chat_id=new_id,
                **correlation,
                **(await self._session_projection.attach_fields(webui_session_key(new_id))),
            )
            await self._transport.webui_send_event(
                connection,
                "session_updated",
                chat_id=new_id,
                scope="metadata",
                workspace_scope=scope.payload(),
            )
            await self._outbound.hydrate(new_id)
            return
        if command_type == "new_temporary_chat":
            try:
                new_id = await self._temporary_chats.create(
                    connection,
                    trusted_webui=connection in self._webui_connections,
                    ptc_mode=envelope.get("ptc_mode", False),
                )
            except TemporaryChatError as exc:
                await self._transport.webui_send_event(connection, "error", detail=exc.detail, **correlation)
                return
            self._transport.webui_attach(connection, new_id)
            await self._transport.webui_send_event(
                connection,
                "attached",
                chat_id=new_id,
                temporary=True,
                **correlation,
            )
            return
        if command_type == "fork_chat":
            await handle_webui_fork_chat(self, connection, envelope)
            return
        if command_type == "discard_temporary_chat":
            chat_id = envelope.get("chat_id")
            if not is_valid_webui_chat_id(chat_id):
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail="invalid temporary chat_id",
                )
                return
            try:
                await self.discard_owned_chat(connection, chat_id)
            except TemporaryChatError as exc:
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail=exc.detail,
                    chat_id=chat_id,
                )
            return
        if command_type == "attach":
            chat_id = envelope.get("chat_id")
            if not is_valid_webui_chat_id(chat_id):
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail="invalid chat_id",
                )
                return
            try:
                self._temporary_chats.validate_attach(chat_id)
            except TemporaryChatError as exc:
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail=exc.detail,
                    chat_id=chat_id,
                )
                return
            self._transport.webui_attach(connection, chat_id)
            await self._transport.webui_send_event(
                connection,
                "attached",
                chat_id=chat_id,
                **(await self._session_projection.attach_fields(webui_session_key(chat_id))),
            )
            await self._outbound.hydrate(chat_id)
            return
        if command_type == "set_sidebar_state":
            if connection not in self._webui_connections:
                await self._transport.webui_send_event(connection, "error", detail="access_denied")
                return
            state = envelope.get("state")
            if not isinstance(state, dict):
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail="invalid_sidebar_state",
                )
                return
            try:
                saved_state = await asyncio.to_thread(
                    write_webui_sidebar_state,
                    cast(dict[str, Any], state),
                )
            except (OSError, ValueError):
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail="invalid_sidebar_state",
                )
                return
            await self.broadcast_webui_event("sidebar_state_updated", state=saved_state)
            return
        if command_type == "set_workspace_scope":
            chat_id = envelope.get("chat_id")
            if not is_valid_webui_chat_id(chat_id):
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail="invalid chat_id",
                )
                return
            try:
                self._temporary_chats.validate_workspace_update(chat_id)
            except TemporaryChatError as exc:
                await self._transport.webui_send_event(
                    connection,
                    "error",
                    detail=exc.detail,
                    chat_id=chat_id,
                )
                return
            scope = await self.messages.workspace_scope_or_error(
                connection,
                lambda: self._workspaces.scope_for_set_request(
                    envelope,
                    chat_id=chat_id,
                    chat_running=websocket_turn_wall_started_at(chat_id) is not None,
                    can_change_project=self.workspace_project_selection_available(connection),
                ),
                chat_id=chat_id,
            )
            if scope is None:
                return
            if (
                await self.messages.workspace_scope_or_error(
                    connection,
                    lambda: self._workspaces.stage_scope(chat_id, scope),
                    chat_id=chat_id,
                )
                is None
            ):
                return
            await self._outbound.session_updated(chat_id, scope="metadata")
            await self._transport.webui_send_event(
                connection,
                "session_updated",
                chat_id=chat_id,
                scope="metadata",
                workspace_scope=scope.payload(),
            )
            return
        if command_type == "message":
            await self.messages.dispatch(connection, client_id, envelope)
            return
        await self._transport.webui_send_event(
            connection,
            "error",
            detail=f"unknown type: {command_type!r}",
        )

    async def close(self) -> None:
        """Cancel command work and release application-owned gateway state."""
        await self.requests.close()
        await self._http_router.settings_routes.close()
        self.gateway.tokens.clear()
        self.gateway.endpoint.clear()
        self._temporary_chats.close()
