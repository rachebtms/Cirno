"""Sidebar HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.sidebar_state import (
    normalize_webui_sidebar_state,
    read_webui_sidebar_state,
    write_webui_sidebar_state,
)
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import _mutation_payload

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class SidebarRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    def _handle_webui_sidebar_state(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        try:
            return _http_json_response(read_webui_sidebar_state())
        except (OSError, ValueError):
            self.server._log.exception("failed to read webui conversation preferences")
            return _http_error(500, "failed to read conversation preferences")

    async def _handle_webui_sidebar_state_update(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        payload = _mutation_payload(request)
        state_value = payload.get("state") if payload is not None else None
        if state_value is None:
            return _http_error(400, "missing state")
        if not isinstance(state_value, dict):
            return _http_error(400, "state must be an object")
        from cirno_core.session.sqlite_store import SessionConflictError

        state = normalize_webui_sidebar_state(state_value)
        state["title_overrides"].pop(ROUTER_SESSION_KEY, None)
        try:
            if self.server.session_manager is not None:
                for key, title in state["title_overrides"].items():
                    header = await self.server.session_manager.state.read_header(key)
                    if header is None:
                        continue
                    if header.metadata.get("title") == title and header.metadata.get(
                        "title_user_edited"
                    ):
                        continue
                    await self.server.session_manager.state.update_metadata(
                        key,
                        {"title": title, "title_user_edited": True},
                        expected_generation=header.generation,
                    )
            state = write_webui_sidebar_state(state)
        except SessionConflictError:
            return _http_error(
                409, "conversation changed while saving its title; reload and try again"
            )
        except ValueError as e:
            return _http_error(400, str(e))
        except OSError:
            self.server._log.exception("failed to write webui sidebar state")
            return _http_error(500, "failed to write sidebar state")
        return _http_json_response(state)
