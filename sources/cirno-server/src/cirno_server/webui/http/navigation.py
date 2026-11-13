"""Navigation HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from cirno_core.command.builtin.catalog import builtin_command_palette
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import _NO_STORE_HEADERS, _is_websocket_channel_session_key, _mutation_payload

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class NavigationRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    async def _dispatch_misc_routes(
        self, connection: Any, request: WsRequest, got: str
    ) -> Response | None:
        if got == "/v0/sessions":
            return await self.server.sessions_routes._handle_sessions_list(request)
        if got == "/v0/commands":
            return self.server.navigation_routes._handle_commands(request)
        if got.startswith("/v0/workspaces/files/"):
            return await self.server.files_routes._handle_workspace_files(
                connection, request, got.rsplit("/", 1)[-1]
            )
        if got == "/v0/workspaces/favorite":
            return self.server.files_routes._handle_workspace_favorite(connection, request)
        if got == "/v0/workspaces/resolve-project":
            return await self.server.files_routes._handle_workspace_resolve_project(
                connection, request
            )
        if got == "/v0/workspaces/directories":
            return await self.server.files_routes._handle_workspace_directories(connection, request)
        if got == "/v0/workspaces":
            return self.server.files_routes._handle_workspaces(connection, request)
        if got == "/v0/webui/skills/search":
            return await self.server.skills_routes._handle_webui_skills_search(request)
        if got == "/v0/webui/skills/trending":
            return await self.server.skills_routes._handle_webui_skills_trending(request)
        if got == "/v0/webui/skills/trends":
            return await self.server.skills_routes._handle_webui_skill_trends(request)
        if got == "/v0/webui/skills/install":
            return await self.server.skills_routes._handle_webui_skill_install(request)
        if got == "/v0/webui/skills/update":
            return await self.server.skills_routes._handle_webui_skill_update(request)
        if got == "/v0/webui/skills/delete":
            return await self.server.skills_routes._handle_webui_skill_delete(request)
        if got == "/v0/webui/skills":
            return await self.server.skills_routes._handle_webui_skills(request)
        m = re.match(r"^/v0/webui/skills/([^/]+)$", got)
        if m:
            return await self.server.skills_routes._handle_webui_skill_detail(request, m.group(1))
        if got == "/v0/webui/sidebar-state":
            return self.server.sidebar_routes._handle_webui_sidebar_state(request)
        if got == "/v0/webui/sidebar-state/update":
            return await self.server.sidebar_routes._handle_webui_sidebar_state_update(request)
        return None

    def _handle_commands(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        return _http_json_response({"commands": builtin_command_palette(include_hidden=True)})

    async def _handle_session_context(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        key = (_mutation_payload(request) or {}).get("session_key")
        if not isinstance(key, str) or not _is_websocket_channel_session_key(key):
            return _http_error(400, "Invalid session key")
        if self.server.context_usage is None:
            return _http_error(503, "Context measurement is unavailable")
        try:
            result = await self.server.context_usage(key)
        except KeyError:
            return _http_error(404, "Session not found")
        return _http_json_response(result, extra_headers=_NO_STORE_HEADERS)
