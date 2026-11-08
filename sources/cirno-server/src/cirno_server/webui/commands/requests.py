"""Connection-owned request delivery and cross-reconnect mutation receipts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable
from typing import Any, cast

from cirno_core.security.workspace_access import WorkspaceScopeError
from cirno_core.session.session_identity import is_valid_webui_chat_id, webui_session_key
from cirno_core.session.webui_turns.activity import websocket_turn_wall_started_at
from loguru import logger
from websockets.asyncio.server import ServerConnection

from cirno_server.webui.attachments import inspect_local_attachment
from cirno_server.webui.file_preview import WebUIFilePreviewError, preview_request_payload
from cirno_server.webui.services import ServerServices
from cirno_server.webui.temporary_chats import TemporaryChatError

from .contracts import (
    BroadcastWebUIEvent,
    WebUICommandTransport,
    WebUIRequestOperation,
    WebUIRequestResult,
    is_request_id,
)

_WEBUI_REQUEST_CACHE_TTL_S = 5 * 60.0
_WEBUI_REQUEST_CACHE_MAX = 256


class WebUIRequests:
    def __init__(
        self,
        transport: WebUICommandTransport,
        services: ServerServices,
        *,
        can_select_workspace: Callable[[ServerConnection], bool],
        broadcast: BroadcastWebUIEvent,
    ) -> None:
        self._transport = transport
        self._http_router = services.http
        self._media = services.media
        self._uploads = services.uploads
        self._workspaces = services.workspaces
        self._temporary_chats = services.temporary_chats
        self._webui_connections = services.endpoint.webui_connections
        self._can_select_workspace = can_select_workspace
        self._broadcast = broadcast
        self.tasks: dict[tuple[ServerConnection, str], asyncio.Task[None]] = {}
        self.operations: dict[str, WebUIRequestOperation] = {}
        self.locks: dict[ServerConnection, asyncio.Lock] = {}

    async def start(
        self,
        connection: ServerConnection,
        envelope: dict[str, Any],
    ) -> None:
        request_id = envelope.get("request_id")
        if not is_request_id(request_id):
            await self._transport.webui_send_event(
                connection,
                "error",
                detail="invalid webui request_id",
            )
            return
        if connection not in self._webui_connections:
            await self.respond(
                connection,
                request_id,
                status=403,
                message="access_denied",
            )
            return

        action = envelope.get("action")
        payload = envelope.get("payload")
        if (
            not isinstance(action, str)
            or re.fullmatch(
                r"[a-z][a-z0-9_.]{0,127}",
                action,
            )
            is None
        ):
            await self.respond(
                connection,
                request_id,
                status=400,
                message="invalid WebUI mutation action",
            )
            return
        if not isinstance(payload, dict):
            await self.respond(
                connection,
                request_id,
                status=400,
                message="WebUI mutation payload must be an object",
            )
            return

        payload = cast(dict[str, Any], payload)
        if action == "attachment.inspect":
            # Read-only and connection-scoped: never retain filesystem results in
            # the mutation replay cache. Send admission always checks again.
            chat_id, path = payload.get("chat_id"), payload.get("path")
            if (chat_id is not None and not is_valid_webui_chat_id(chat_id)) or not isinstance(
                path, str
            ):
                await self.respond(
                    connection,
                    request_id,
                    status=400,
                    message="invalid attachment request",
                )
                return
            try:
                if chat_id is None:
                    scope = await self._workspaces.scope_for_new_chat(
                        payload,
                        can_change_project=self._can_select_workspace(connection),
                    )
                else:
                    policy = self._temporary_chats.message_policy(connection, chat_id, "")
                    scope = (
                        policy.workspace_scope
                        if policy is not None
                        else (
                            await self._workspaces.scope_for_message(
                                payload,
                                chat_id=chat_id,
                                chat_running=websocket_turn_wall_started_at(chat_id) is not None,
                                can_change_project=self._can_select_workspace(connection),
                            )
                        )
                    )
                result = await asyncio.to_thread(
                    inspect_local_attachment,
                    path,
                    scope=scope,
                    limits=self._uploads.store.limits,
                )
            except (TemporaryChatError, WorkspaceScopeError, WebUIFilePreviewError) as exc:
                await self.respond(
                    connection,
                    request_id,
                    status=getattr(exc, "status", 404),
                    message=str(exc),
                )
            else:
                await self.respond(
                    connection,
                    request_id,
                    result={
                        **result,
                        "url": self._media.local_attachment_url(
                            result["path"],
                            session_key=webui_session_key(chat_id),
                        )
                        if chat_id is not None
                        else "",
                    },
                )
            return

        if action == "temporary_chat.file_preview":
            # Connection-owned, read-only, and deliberately outside the mutation
            # replay cache: private paths/content must not outlive this request.
            preview_payload = cast(dict[str, object], payload)
            chat_id = preview_payload.get("chat_id")
            path = preview_payload.get("path")
            probe = preview_payload.get("probe") is True
            metadata_only = preview_payload.get("metadata") is True
            if not isinstance(chat_id, str) or not isinstance(path, str):
                await self.respond(
                    connection,
                    request_id,
                    status=400,
                    message="invalid preview request",
                )
                return
            try:
                policy = self._temporary_chats.message_policy(connection, chat_id, "")
                if policy is None:
                    raise TemporaryChatError("temporary_chat_unavailable")
                result = await asyncio.to_thread(
                    preview_request_payload,
                    path,
                    scope=policy.workspace_scope,
                    metadata_only=metadata_only,
                    probe=probe,
                    media_url=lambda target: self._media.workspace_media_url(
                        str(target),
                        scope=policy.workspace_scope,
                        session_key=webui_session_key(chat_id),
                    ),
                )
            except TemporaryChatError as exc:
                await self.respond(
                    connection,
                    request_id,
                    status=404,
                    message=exc.detail,
                )
            except WebUIFilePreviewError as exc:
                if probe and not metadata_only and exc.status in {400, 403, 404, 413, 415}:
                    await self.respond(
                        connection,
                        request_id,
                        result={"available": False},
                    )
                else:
                    await self.respond(
                        connection,
                        request_id,
                        status=exc.status,
                        message=exc.message,
                    )
            else:
                await self.respond(connection, request_id, result=result)
            return

        payload_digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).digest()
        self.prune()
        operation = self.operations.get(request_id)
        is_replay = operation is not None
        if operation is not None and (
            operation.action != action or operation.payload_digest != payload_digest
        ):
            await self.respond(
                connection,
                request_id,
                status=409,
                message="request_id was already used for a different WebUI mutation",
            )
            return
        if operation is None:
            operation_task = asyncio.create_task(
                self.execute(
                    connection,
                    action,
                    payload,
                )
            )
            new_operation = WebUIRequestOperation(
                action=action,
                payload_digest=payload_digest,
                task=operation_task,
            )
            operation = new_operation
            self.operations[request_id] = new_operation

            def mark_complete(_task: asyncio.Task[WebUIRequestResult]) -> None:
                current = self.operations.get(request_id)
                if current is not new_operation:
                    return
                new_operation.completed_at = time.monotonic()
                if action == "workbench.action" and payload.get("action") in {
                    "terminal.read",
                    "trace.events",
                    "trace.detail",
                    "credentials.list",
                    "credentials.describe",
                    "credentials.reveal",
                }:
                    # Poll output and revealed secrets must not accumulate in the
                    # five-minute mutation replay cache. In-flight work is still
                    # owned and drained exactly like every other request.
                    self.operations.pop(request_id, None)
                self.prune()

            operation_task.add_done_callback(mark_complete)

        key = (connection, request_id)
        if key in self.tasks:
            return
        delivery_task = asyncio.create_task(
            self.deliver(
                connection,
                request_id,
                operation.task,
                sequence=is_replay,
            )
        )
        self.tasks[key] = delivery_task

    def prune(self) -> None:
        now = time.monotonic()
        for request_id, operation in tuple(self.operations.items()):
            if (
                operation.completed_at is not None
                and now - operation.completed_at >= _WEBUI_REQUEST_CACHE_TTL_S
            ):
                self.operations.pop(request_id, None)

        completed = sorted(
            (
                (operation.completed_at, request_id)
                for request_id, operation in self.operations.items()
                if operation.completed_at is not None
            ),
            key=lambda item: item[0],
        )
        for _, request_id in completed[:-_WEBUI_REQUEST_CACHE_MAX]:
            self.operations.pop(request_id, None)

    def discard_connection_if_idle(self, connection: ServerConnection) -> None:
        if connection in self._webui_connections:
            return
        if any(task_connection is connection for task_connection, _ in self.tasks):
            return
        self.locks.pop(connection, None)

    async def deliver(
        self,
        connection: ServerConnection,
        request_id: str,
        operation_task: asyncio.Task[WebUIRequestResult],
        *,
        sequence: bool = False,
    ) -> None:
        try:
            if sequence:
                lock = self.locks.setdefault(connection, asyncio.Lock())
                async with lock:
                    result = await asyncio.shield(operation_task)
                    await self.respond(
                        connection,
                        request_id,
                        result=result.result,
                        status=result.status,
                        message=result.message,
                    )
                return
            result = await asyncio.shield(operation_task)
            await self.respond(
                connection,
                request_id,
                result=result.result,
                status=result.status,
                message=result.message,
            )
        finally:
            self.tasks.pop((connection, request_id), None)
            self.discard_connection_if_idle(connection)

    async def execute(
        self,
        connection: ServerConnection,
        action: str,
        payload: dict[str, Any],
    ) -> WebUIRequestResult:
        try:
            lock = self.locks.setdefault(connection, asyncio.Lock())
            async with lock:
                response = await self._http_router.dispatch_webui_mutation(
                    connection,
                    action,
                    payload,
                )
                status = response.status_code
                body = bytes(response.body).decode("utf-8", errors="replace").strip()
                if 200 <= status < 300:
                    try:
                        result = json.loads(body)
                    except json.JSONDecodeError:
                        return WebUIRequestResult(
                            status=502,
                            message="WebUI mutation returned an invalid response",
                        )
                    if action == "preferences.update" and isinstance(result, dict):
                        await self._broadcast("preferences_updated", preferences=result)
                    if action == "sidebar.update" and isinstance(result, dict):
                        await self._broadcast(
                            "sidebar_state_updated",
                            state=result,
                        )
                    return WebUIRequestResult(result=result)
                return WebUIRequestResult(
                    status=status,
                    message=body or response.reason_phrase,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WebUI mutation '{}' failed", action)
            return WebUIRequestResult(
                status=500,
                message="WebUI mutation failed",
            )

    async def respond(
        self,
        connection: ServerConnection,
        request_id: str,
        *,
        result: Any = None,
        status: int | None = None,
        message: str | None = None,
    ) -> None:
        if status is None:
            await self._transport.webui_send_event(
                connection,
                "webui_response",
                request_id=request_id,
                ok=True,
                result=result,
            )
            return
        await self._transport.webui_send_event(
            connection,
            "webui_response",
            request_id=request_id,
            ok=False,
            error={
                "status": status,
                "message": message or "WebUI mutation failed",
            },
        )

    async def close(self) -> None:
        """Drain accepted mutations and their deliveries before releasing request state."""
        delivery_tasks = tuple(self.tasks.values())
        operation_tasks = tuple(operation.task for operation in self.operations.values())
        for task in (*delivery_tasks, *operation_tasks):
            task.cancel()
        if delivery_tasks:
            await asyncio.gather(*delivery_tasks, return_exceptions=True)
        if operation_tasks:
            await asyncio.gather(*operation_tasks, return_exceptions=True)
        self.tasks.clear()
        self.locks.clear()
        self.operations.clear()
