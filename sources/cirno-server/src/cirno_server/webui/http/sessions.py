"""Sessions HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.session_handles import SessionHandle, SessionHandleResolver
from cirno_core.session.session_identity import is_webui_session_key
from cirno_core.triggers.local_types import LocalTrigger
from cirno_server.webui.file_preview import (
    WebUIFilePreviewError,
    preview_request_payload,
)
from cirno_server.webui.http_utils import combined_list_header as _combined_list_header
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import parse_query as _parse_query
from cirno_server.webui.http_utils import query_first as _query_first
from cirno_server.webui.session_automations import (
    serialize_automation_jobs,
    session_automation_jobs,
    session_automations_payload,
)
from cirno_server.webui.session_context import session_context_payload
from cirno_server.webui.session_list_index import (
    WEBUI_SESSION_INDEX_INTERNAL_FIELDS,
    indexed_workspace_scope,
    list_webui_sessions,
)
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import (
    _NO_STORE_HEADERS,
    _decode_api_key,
    _is_websocket_channel_session_key,
    _request_query,
)

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class SessionsRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    async def _dispatch_session_routes(self, request: WsRequest, got: str) -> Response | None:
        m = re.fullmatch(r"/v0/sessions/([^/]+)/webui-thread/prompts", got)
        if m:
            return await self.server.history_routes._project_session_history(
                request, m.group(1), self.server.history_routes._handle_prompt_index_get
            )

        m = re.match(r"^/v0/sessions/([^/]+)/webui-thread/trace-detail$", got)
        if m:
            return await self.server.history_routes._project_session_history(
                request, m.group(1), self.server.history_routes._handle_webui_trace_detail_get
            )

        m = re.match(r"^/v0/sessions/([^/]+)/webui-thread$", got)
        if m:
            return await self.server.history_routes._handle_webui_thread_get_async(
                request, m.group(1)
            )

        m = re.match(r"^/v0/sessions/([^/]+)/context$", got)
        if m:
            return await self.server.sessions_routes._handle_session_context_get(
                request, m.group(1)
            )

        m = re.match(r"^/v0/sessions/([^/]+)/file-preview$", got)
        if m:
            return self.server.sessions_routes._handle_file_preview(request, m.group(1))

        m = re.match(r"^/v0/sessions/([^/]+)/automations$", got)
        if m:
            return self.server.sessions_routes._handle_session_automations(request, m.group(1))

        m = re.fullmatch(r"/v0/sessions/([^/]+)/subagents/([^/]+)/webui-thread", got)
        if m:
            return await asyncio.to_thread(
                self.server.recovery_routes._handle_subagent_thread_get,
                request,
                m.group(1),
                m.group(2),
            )

        m = re.fullmatch(r"/v0/sessions/([^/]+)/subagents", got)
        if m:
            return await self.server.recovery_routes._handle_subagents_get(request, m.group(1))

        m = re.match(r"^/v0/sessions/([^/]+)/delete$", got)
        if m:
            return await self.server.sessions_routes._handle_session_delete(request, m.group(1))

        return None

    async def _handle_session_context_get(self, request: WsRequest, key: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        if self.server.session_manager is None:
            return _http_error(503, "session manager unavailable")
        session = await asyncio.to_thread(
            self.server.session_manager.read_session_snapshot,
            decoded_key,
        )
        if session is None:
            return _http_error(404, "session not found")
        return _http_json_response(session_context_payload(session))

    async def _handle_sessions_list(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if self.server.session_manager is None:
            return _http_error(503, "session manager unavailable")
        accept_encoding = _combined_list_header(request.headers, "Accept-Encoding")

        def render(stored: list[dict[str, Any]]) -> Response | None:
            payload = self.server.sessions_routes._sessions_list_from_snapshot(stored)
            if payload is None:
                return None
            return _http_json_response(payload, accept_encoding=accept_encoding)

        response = await self.server.session_manager.state.query_metadata(render)
        if response is None:
            handles = await SessionHandleResolver(self.server.session_manager).alist_all_by_key()

            def render_allocated(stored: list[dict[str, Any]]) -> Response:
                return _http_json_response(
                    self.server.sessions_routes._sessions_list_payload(handles, stored),
                    accept_encoding=accept_encoding,
                )

            response = await self.server.session_manager.state.query_metadata(render_allocated)
        return response

    def _sessions_list_from_snapshot(
        self,
        stored_sessions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        assert self.server.session_manager is not None
        handles = SessionHandleResolver(self.server.session_manager).handles_from_metadata(
            stored_sessions
        )
        if handles is None:
            return None
        return self.server.sessions_routes._sessions_list_payload(handles, stored_sessions)

    def _sessions_list_payload(
        self,
        handles: dict[str, SessionHandle],
        stored_sessions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        assert self.server.session_manager is not None
        from cirno_core.session.webui_turns.activity import websocket_turn_wall_started_at

        sessions = list_webui_sessions(self.server.session_manager, stored_sessions)
        cleaned: list[dict[str, Any]] = []
        default_scope: WorkspaceScope | None = None
        scopes: dict[str, WorkspaceScope] = {}
        for s in sessions:
            key = s.get("key")
            if not (isinstance(key, str) and is_webui_session_key(key)):
                continue
            row = {
                k: v
                for k, v in s.items()
                if k != "path" and k not in WEBUI_SESSION_INDEX_INTERNAL_FIELDS
            }
            # Keep the additive recovery field absent for ordinary sessions so
            # older clients and compact list responses stay unchanged.
            if row.get("recovery_state") is None:
                row.pop("recovery_state", None)
            chat_id = key.split(":", 1)[1]
            started_at = websocket_turn_wall_started_at(chat_id)
            if started_at is not None:
                row["run_started_at"] = started_at
            if default_scope is None:
                default_scope = self.server.workspaces.default_scope()
            scope_present, raw_scope = indexed_workspace_scope(s)
            if scope_present:
                scope_key = json.dumps(raw_scope, ensure_ascii=False, sort_keys=True)
                scope = scopes.get(scope_key)
                if scope is None:
                    scope = self.server.workspaces.scope_for_indexed_metadata(
                        raw_scope,
                        scope_present=True,
                        default_scope=default_scope,
                    )
                    scopes[scope_key] = scope
            else:
                scope = default_scope
            row["workspace_scope"] = scope.payload()
            row["project_locked"] = True
            handle = handles.get(key)
            if handle is not None:
                row["handle"] = handle.public_payload()
            cleaned.append(row)
        return {"sessions": cleaned}

    def _handle_file_preview(self, request: WsRequest, key: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        query = _parse_query(request.path)
        path = _query_first(query, "path")
        is_probe = _query_first(query, "probe") == "1"
        metadata_only = _query_first(query, "metadata") == "1"
        try:
            scope = self.server.workspaces.scope_for_session_key(decoded_key)
            payload = preview_request_payload(path, scope=scope, metadata_only=metadata_only, probe=is_probe,
                media_url=lambda target: self.server.media.workspace_media_url(
                    str(target), scope=scope, session_key=decoded_key,
                ))
        except WebUIFilePreviewError as e:
            if is_probe and not metadata_only and e.status in {400, 403, 404, 413, 415}:
                return _http_json_response({"available": False}, extra_headers=_NO_STORE_HEADERS)
            return _http_error(e.status, e.message)
        return _http_json_response(payload, extra_headers=_NO_STORE_HEADERS)

    def _handle_session_automations(self, request: WsRequest, key: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        pending_job_ids = self.server.automations_routes._pending_automation_ids_for_session(
            decoded_key
        )
        return _http_json_response(
            session_automations_payload(
                self.server.cron_service,
                decoded_key,
                local_trigger_store=self.server.local_trigger_store,
                session_manager=self.server.session_manager,
                pending_job_ids=pending_job_ids,
            )
        )

    async def _handle_session_delete(self, request: WsRequest, key: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if self.server.session_manager is None:
            return _http_error(503, "session manager unavailable")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        if decoded_key == ROUTER_SESSION_KEY:
            return _http_error(409, "The Router conversation cannot be deleted")
        query = _request_query(request)
        delete_automations = (_query_first(query, "delete_automations") or "").lower()
        automation_jobs = session_automation_jobs(
            self.server.cron_service,
            decoded_key,
            local_trigger_store=self.server.local_trigger_store,
        )
        if automation_jobs and delete_automations not in {"1", "true", "yes"}:
            return _http_json_response(
                {
                    "deleted": False,
                    "blocked_by_automations": True,
                    "automations": serialize_automation_jobs(automation_jobs, trigger_root=self.server.local_trigger_store.root if self.server.local_trigger_store is not None else None),
                }
            )
        if automation_jobs:
            for job in automation_jobs:
                if isinstance(job, LocalTrigger):
                    if self.server.local_trigger_store is not None:
                        await asyncio.to_thread(self.server.local_trigger_store.delete, job.id)
                elif self.server.cron_service is not None:
                    self.server.cron_service.remove_job(job.id)
        draft_deleted = self.server.workspaces.discard_draft_scope(decoded_key)
        if self.server.discard_session is not None:
            await self.server.discard_session(decoded_key)
        elif self.server.subagent_manager is not None:
            await self.server.subagent_manager.cancel_by_session(decoded_key)
        session_deleted = await self.server.session_manager.state.delete(decoded_key)
        return _http_json_response({"deleted": bool(draft_deleted or session_deleted)})
