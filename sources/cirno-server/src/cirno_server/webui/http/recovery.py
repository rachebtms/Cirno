"""Recovery HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from cirno_core.agent.subagents.contracts import SubagentControlError
from cirno_core.agent.subagents.status import SubagentSessionError
from cirno_core.session.recovery.contracts import RecoveryActionError
from cirno_core.session.session_identity import is_webui_session_key
from cirno_core.session.transcript import build_session_thread_response
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import (
    _NO_STORE_HEADERS,
    _WEBUI_MUTATION_REQUEST_ATTR,
    _decode_api_key,
    _mutation_payload,
)

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class RecoveryRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    async def _dispatch_recovery_route(
        self,
        request: WsRequest,
        path: str,
    ) -> Response | None:
        match = re.fullmatch(r"/v0/webui/recovery/(continue|dismiss)", path)
        if match is None:
            return None
        if not getattr(request, _WEBUI_MUTATION_REQUEST_ATTR, False):
            return _http_error(405, "WebUI recovery actions require an authenticated WebSocket")
        if self.server.recovery_action is None:
            return _http_error(503, "WebUI recovery is unavailable")
        payload = _mutation_payload(request)
        if payload is None:
            return _http_error(400, "invalid recovery payload")
        try:
            result = await self.server.recovery_action(match.group(1), payload)
        except RecoveryActionError as exc:
            return _http_error(exc.status, str(exc))
        return _http_json_response(result)

    async def _handle_subagents_get(self, request: WsRequest, key: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        session_key = _decode_api_key(key)
        if session_key is None:
            return _http_error(400, "invalid session key")
        if not is_webui_session_key(session_key):
            return _http_error(404, "session not found")
        if self.server.subagent_manager is None:
            return _http_error(503, "subagent manager unavailable")
        try:
            statuses = await self.server.subagent_manager.read_statuses_for_session(session_key)
        except (OSError, SubagentSessionError):
            return _http_error(503, "task history unavailable")
        return _http_json_response(
            {
                "tasks": [status.as_dict() for status in statuses.values()],
            },
            extra_headers=_NO_STORE_HEADERS,
        )

    async def _handle_subagent_cancel(self, request: WsRequest) -> Response:
        if not getattr(request, _WEBUI_MUTATION_REQUEST_ATTR, False):
            return _http_error(405, "Subagent cancellation requires an authenticated WebSocket")
        if self.server.subagent_manager is None:
            return _http_error(503, "subagent manager unavailable")
        payload = _mutation_payload(request)
        if payload is None:
            return _http_error(400, "invalid subagent cancellation payload")
        session_key, task_id = payload.get("session_key"), payload.get("task_id")
        if not isinstance(session_key, str) or not is_webui_session_key(session_key):
            return _http_error(400, "invalid session key")
        if not isinstance(task_id, str) or not task_id.strip():
            return _http_error(400, "missing task id")
        try:
            status = await self.server.subagent_manager.cancel(task_id, session_key)
        except SubagentControlError:
            return _http_error(404, "task unavailable")
        except (OSError, SubagentSessionError):
            return _http_error(503, "task history unavailable")
        return _http_json_response(status.as_dict(), extra_headers=_NO_STORE_HEADERS)

    def _handle_subagent_thread_get(self, request: WsRequest, key: str, task_id: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        session_key, decoded_task_id = _decode_api_key(key), _decode_api_key(task_id)
        if session_key is None or decoded_task_id is None:
            return _http_error(400, "invalid task key")
        if not is_webui_session_key(session_key):
            return _http_error(404, "task unavailable")
        if self.server.subagent_manager is None:
            return _http_error(503, "task history unavailable")
        try:
            status, child = self.server.subagent_manager.read_session(decoded_task_id, session_key)
        except SubagentControlError:
            return _http_error(404, "task unavailable")
        except (OSError, SubagentSessionError):
            return _http_error(503, "task history unavailable")
        scope = self.server.workspaces.scope_for_session_key(session_key)
        data = build_session_thread_response(
            child,
            active=status.state in {"queued", "running", "stopping"},
            latency_ms=(
                int(max(0.0, status.finished_at - status.started_at) * 1000)
                if status.finished_at is not None
                else None
            ),
            augment_user_media=lambda paths, local: self.server.media.augment_transcript_user_media(
                paths, local, session_key=session_key
            ),
            augment_assistant_media=self.server.media.augment_transcript_media,
            augment_assistant_text=lambda text: self.server.media.rewrite_local_markdown_images(
                text,
                workspace_path=scope.project_path,
            ),
        )
        return _http_json_response(data, extra_headers=_NO_STORE_HEADERS)
