"""Files HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from cirno_core.security.workspace_access import WorkspaceScopeError
from cirno_server.webui.file_preview import WebUIFilePreviewError
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import parse_query as _parse_query
from cirno_server.webui.http_utils import query_first as _query_first
from cirno_server.webui.workspace_browser import browse_workspace_directories
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import _NO_STORE_HEADERS, _is_websocket_channel_session_key, _mutation_payload

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class FilesRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    async def _handle_workspace_files(
        self, connection: Any, request: WsRequest, action: str
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        from cirno_server.webui.workspace_files import (
            create_workspace_entry,
            list_workspace_files,
            read_workspace_file,
            save_workspace_file,
        )

        payload = _mutation_payload(request) or {}
        key = payload.get("session_key")
        if key is not None and (
            not isinstance(key, str) or not _is_websocket_channel_session_key(key)
        ):
            return _http_error(400, "Invalid session key")
        path = payload.get("path", "")
        if not isinstance(path, str):
            return _http_error(400, "Path must be text")
        try:
            scope = await self.server.workspaces.scope_from_envelope(
                payload,
                session_key=key,
                can_change_project=self.server.workspace_project_selection_available(connection),
            )
            if action == "list":
                query = payload.get("query", "")
                if not isinstance(query, str):
                    return _http_error(400, "Search must be text")
                result = await asyncio.to_thread(
                    list_workspace_files,
                    path,
                    scope=scope,
                    query=query,
                    show_hidden=payload.get("show_hidden") is True,
                )
            elif action == "read":
                result = await asyncio.to_thread(read_workspace_file, path, scope=scope,
                    media_url=lambda target: self.server.media.workspace_media_url(
                        str(target), scope=scope, session_key=key,
                    ))
            elif action == "save":
                content, revision = payload.get("content"), payload.get("revision")
                if not isinstance(content, str) or not isinstance(revision, str):
                    return _http_error(400, "Content and revision are required")
                result = await asyncio.to_thread(
                    save_workspace_file, path, content, revision, scope=scope
                )
            elif action == "create":
                kind = payload.get("kind")
                if kind not in {"file", "directory"}:
                    return _http_error(400, "Choose a file or directory")
                result = await asyncio.to_thread(create_workspace_entry, path, kind, scope=scope)
            else:
                return _http_error(404, "File operation not found")
        except (WebUIFilePreviewError, WorkspaceScopeError) as exc:
            return _http_error(exc.status, str(exc))
        except PermissionError as exc:
            return _http_error(403, str(exc))
        except FileExistsError as exc:
            return _http_error(409, str(exc))
        except (FileNotFoundError, NotADirectoryError) as exc:
            return _http_error(404, str(exc))
        except OSError as exc:
            self.server._log.exception("Workspace file operation failed")
            return _http_error(500, str(exc))
        return _http_json_response(result, extra_headers=_NO_STORE_HEADERS)

    def _handle_workspaces(self, connection: Any, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        return _http_json_response(
            self.server.workspaces.payload(
                can_change_project=self.server.workspace_project_selection_available(connection),
            )
        )

    def _handle_workspace_favorite(self, connection: Any, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if not self.server.workspace_project_selection_available(connection):
            return _http_error(403, "project selection is unavailable for this connection")
        payload = _mutation_payload(request) or {}
        try:
            favorites = self.server.workspaces.set_favorite_project(
                payload.get("path"), payload.get("pinned")
            )
        except WorkspaceScopeError as exc:
            return _http_error(exc.status, exc.message)
        except OSError:
            return _http_error(500, "could not save favorite folders")
        return _http_json_response({"favorite_projects": favorites})

    async def _handle_workspace_resolve_project(
        self, connection: Any, request: WsRequest
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if not self.server.workspace_project_selection_available(connection):
            return _http_error(403, "project selection is unavailable for this connection")
        payload = _mutation_payload(request) or {}
        try:
            project = self.server.workspaces.resolve_project(payload.get("path"))
        except WorkspaceScopeError as exc:
            return _http_error(exc.status, exc.message)
        return _http_json_response(project)

    async def _handle_workspace_directories(self, connection: Any, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if not self.server.workspace_project_selection_available(connection):
            return _http_error(403, "project selection is unavailable for this connection")
        query = _parse_query(request.path)
        try:
            payload = await asyncio.to_thread(
                browse_workspace_directories,
                _query_first(query, "path") or "",
                default_workspace=self.server.workspaces.default_scope().project_path,
                query=_query_first(query, "q") or "",
                show_hidden=_query_first(query, "hidden") == "1",
                allow_partial=_query_first(query, "partial") == "1",
            )
        except WorkspaceScopeError as exc:
            return _http_error(exc.status, exc.message)
        return _http_json_response(dict(payload))
