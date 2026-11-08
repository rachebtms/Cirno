"""History HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import TYPE_CHECKING, Any, cast

from cirno_core.session.display_history import HistoryReader
from cirno_core.session.transcript import (
    TranscriptReplayStats,
    build_webui_thread_response,
    build_webui_trace_detail_response,
    webui_transcript_revision,
)
from cirno_server.webui.http_utils import case_insensitive_header as _case_insensitive_header
from cirno_server.webui.http_utils import combined_list_header as _combined_list_header
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import http_response as _http_response
from cirno_server.webui.http_utils import parse_query as _parse_query
from cirno_server.webui.http_utils import query_first as _query_first
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import (
    _NO_STORE_HEADERS,
    _SLOW_WEBUI_HTTP_LOG_MS,
    _decode_api_key,
    _etag_matches,
    _HistoryProjection,
    _is_websocket_channel_session_key,
    _quoted_etag,
    _WebUIThreadDiagnostics,
)

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class HistoryRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    def _read_session_messages(self, key: str) -> list[dict[str, Any]] | None:
        if self.server.session_manager is None:
            return None
        session_data = self.server.session_manager.read_session_file(key)
        raw_messages = session_data.get("messages") if isinstance(session_data, dict) else None
        if not isinstance(raw_messages, list):
            return None
        return [
            cast(dict[str, Any], message)
            for message in cast(list[Any], raw_messages)
            if isinstance(message, dict)
        ]

    def _read_session_version(self, key: str) -> tuple[str, int] | None:
        return (
            self.server.session_manager.read_session_version(key)
            if self.server.session_manager is not None
            else None
        )

    async def _project_session_history(
        self,
        request: WsRequest,
        key: str,
        project: _HistoryProjection,
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded = _decode_api_key(key)
        if decoded is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded):
            return _http_error(404, "session not found")
        if self.server.session_manager is None:
            return _http_error(503, "session manager unavailable")
        return await self.server.session_manager.state.project_history(
            decoded,
            lambda history: project(request, key, history=history),
        )

    def _handle_prompt_index_get(
        self, request: WsRequest, key: str, *, history: HistoryReader
    ) -> Response:
        from cirno_core.session.transcript import (
            PromptPageRequest,
            prompt_directory_page,
            prompt_index_revision,
        )

        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        query = _parse_query(request.path)
        try:
            options = PromptPageRequest(
                offset=int(_query_first(query, "offset") or "") if "offset" in query else None,
                limit=int(_query_first(query, "limit") or "") if "limit" in query else 64,
                query=_query_first(query, "q") or "",
            )
        except ValueError as exc:
            return _http_error(400, str(exc))
        def page_etag(revision: str | None) -> str | None:
            if revision is None:
                return None
            identity = f"{revision}\0{options.offset}\0{options.limit}\0{options.query}"
            return _quoted_etag(hashlib.sha256(identity.encode()).hexdigest())

        etag = page_etag(prompt_index_revision(
            decoded_key, self.server.history_routes._read_session_version(decoded_key), history=history,
        ))
        if etag and _etag_matches(_case_insensitive_header(request.headers, "If-None-Match"), etag):
            return _http_response(b"", status=304, extra_headers=[*_NO_STORE_HEADERS, ("ETag", etag)])
        data = prompt_directory_page(
            decoded_key, request=options, history=history,
            session_messages_loader=lambda: self.server.history_routes._read_session_messages(decoded_key),
            session_version_loader=lambda: self.server.history_routes._read_session_version(decoded_key),
        )
        etag = page_etag(data["revision"])
        headers = list(_NO_STORE_HEADERS)
        if etag:
            headers.append(("ETag", etag))
        return _http_json_response(
            dict(data),
            accept_encoding=_combined_list_header(request.headers, "Accept-Encoding"),
            extra_headers=headers,
        )

    async def _handle_webui_thread_get_async(self, request: WsRequest, key: str) -> Response:
        diagnostics = _WebUIThreadDiagnostics()
        loop = asyncio.get_running_loop()
        expected_sample_at = loop.time() + 0.05
        max_lag_s = 0.0
        active = True
        timer: asyncio.TimerHandle

        def sample_event_loop_lag() -> None:
            nonlocal expected_sample_at, max_lag_s, timer
            now = loop.time()
            max_lag_s = max(max_lag_s, now - expected_sample_at)
            expected_sample_at = now + 0.05
            if active:
                timer = loop.call_later(0.05, sample_event_loop_lag)

        timer = loop.call_later(0.05, sample_event_loop_lag)
        started = time.perf_counter()

        def project(request: WsRequest, key: str, *, history: HistoryReader) -> Response:
            return self.server.history_routes._handle_webui_thread_get(
                request, key, history=history, diagnostics=diagnostics
            )

        try:
            response = await self.server.history_routes._project_session_history(
                request, key, project
            )
        finally:
            active = False
            timer.cancel()
        diagnostics.total_ms = (time.perf_counter() - started) * 1000
        diagnostics.event_loop_lag_ms = max_lag_s * 1000
        self.server.history_routes._log_webui_thread_diagnostics(response, diagnostics)
        return response

    def _log_webui_thread_diagnostics(
        self,
        response: Response,
        diagnostics: _WebUIThreadDiagnostics,
    ) -> None:
        stats = diagnostics.transcript
        if not (
            diagnostics.total_ms >= _SLOW_WEBUI_HTTP_LOG_MS
            or stats.capped_by_bytes
            or stats.capped_by_records
        ):
            return
        self.server._log.warning(
            "webui thread replay session_hash={} status={} limit={} source_bytes={} "
            "parsed_records={} selected_bytes={} selected_records={} compacted_deltas={} "
            "capped_bytes={} capped_records={} "
            "truncated_turn={} replay_ms={} build_ms={} json_ms={} gzip_ms={} gzip={} "
            "response_bytes={} event_loop_lag_ms={} total_ms={}",
            diagnostics.session_hash or "unknown",
            response.status_code,
            stats.effective_limit,
            stats.source_bytes,
            stats.parsed_records,
            stats.selected_bytes,
            stats.selected_records,
            stats.compacted_delta_records,
            stats.capped_by_bytes,
            stats.capped_by_records,
            stats.truncated_oversized_turn,
            stats.replay_ms,
            round(diagnostics.build_ms, 1),
            round(diagnostics.response.json_encode_ms, 1),
            round(diagnostics.response.gzip_ms, 1),
            diagnostics.response.gzip_enabled,
            diagnostics.response.response_bytes,
            round(diagnostics.event_loop_lag_ms, 1),
            round(diagnostics.total_ms, 1),
        )

    def _handle_webui_thread_get(
        self,
        request: WsRequest,
        key: str,
        *,
        history: HistoryReader,
        diagnostics: _WebUIThreadDiagnostics | None = None,
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        if diagnostics is not None:
            diagnostics.session_hash = hashlib.sha256(decoded_key.encode("utf-8")).hexdigest()[:12]
        scope = self.server.workspaces.scope_for_session_key(decoded_key)

        query = _parse_query(request.path)
        raw_limit = _query_first(query, "limit")
        limit: int | None = None
        if raw_limit is not None and raw_limit.strip():
            try:
                limit = int(raw_limit)
            except ValueError:
                return _http_error(400, "invalid limit")
        direction = _query_first(query, "direction")
        if direction is not None and direction not in {"latest"}:
            return _http_error(400, "invalid direction")
        before = _query_first(query, "before")
        after = _query_first(query, "after")
        from cirno_core.session.transcript import decode_transcript_cursor
        if before is not None and decode_transcript_cursor(before) is None:
            return _http_error(400, "invalid navigation cursor")
        if after is not None:

            if (
                before is not None
                or direction is not None
                or decode_transcript_cursor(after) is None
            ):
                return _http_error(400, "invalid navigation cursor")
        from cirno_core.session.webui_turns.activity import websocket_turn_id, websocket_turn_transcript_persistence_failed, websocket_turn_wall_started_at

        chat_id = decoded_key.split(":", 1)[1]
        active_turn_started_at = websocket_turn_wall_started_at(chat_id)
        active_turn_id = websocket_turn_id(chat_id)
        active_turn_transcript_persistence_failed = websocket_turn_transcript_persistence_failed(
            chat_id
        )
        revision_variant = {
            "active_turn_id": active_turn_id,
            "active_turn_started_at": active_turn_started_at,
            "active_turn_transcript_persistence_failed": (
                active_turn_transcript_persistence_failed
            ),
            "before": before,
            "after": after,
            "direction": direction,
            "gateway_instance": self.server.tokens.instance_id,
            "limit": limit,
            "session_version": self.server.history_routes._read_session_version(decoded_key),
            "workspace_scope": scope.payload(),
        }
        initial_revision = webui_transcript_revision(
            decoded_key, history=history, variant=revision_variant
        )
        if initial_revision is not None:
            etag = _quoted_etag(initial_revision)
            if _etag_matches(_case_insensitive_header(request.headers, "If-None-Match"), etag):
                return _http_response(
                    b"", status=304, extra_headers=[*_NO_STORE_HEADERS, ("ETag", etag)]
                )
        build_started = time.perf_counter()
        replay_stats = (
            diagnostics.transcript if diagnostics is not None else TranscriptReplayStats()
        )
        data = build_webui_thread_response(
            decoded_key,
            history=history,
            augment_user_media=lambda paths, local: self.server.media.augment_transcript_user_media(
                paths, local, session_key=decoded_key
            ),
            augment_assistant_media=self.server.media.augment_transcript_media,
            augment_assistant_text=lambda text: self.server.media.rewrite_local_markdown_images(
                text,
                workspace_path=scope.project_path,
            ),
            session_messages_loader=lambda: self.server.history_routes._read_session_messages(
                decoded_key
            ),
            session_version_loader=lambda: self.server.history_routes._read_session_version(
                decoded_key
            ),
            active_turn_started_at=active_turn_started_at,
            active_turn_id=active_turn_id,
            active_turn_transcript_persistence_failed=(active_turn_transcript_persistence_failed),
            limit=limit,
            direction=direction,
            before=before,
            after=after,
            stats=replay_stats,
        )
        if diagnostics is not None:
            diagnostics.build_ms = (time.perf_counter() - build_started) * 1000
        if data is None:
            return _http_error(404, "webui thread not found")
        data["workspace_scope"] = scope.payload()
        revision_variant["session_version"] = self.server.history_routes._read_session_version(
            decoded_key
        )
        final_revision = webui_transcript_revision(
            decoded_key, history=history, variant=revision_variant
        )
        response_headers = list(_NO_STORE_HEADERS)
        if final_revision is not None and final_revision == initial_revision:
            response_headers.append(("ETag", _quoted_etag(final_revision)))
            data["revision"] = final_revision
        return _http_json_response(
            data,
            accept_encoding=_combined_list_header(request.headers, "Accept-Encoding"),
            extra_headers=response_headers,
            metrics=diagnostics.response if diagnostics is not None else None,
        )

    def _handle_webui_trace_detail_get(
        self, request: WsRequest, key: str, *, history: HistoryReader
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        decoded_key = _decode_api_key(key)
        if decoded_key is None:
            return _http_error(400, "invalid session key")
        if not _is_websocket_channel_session_key(decoded_key):
            return _http_error(404, "session not found")
        detail_ref = _query_first(_parse_query(request.path), "ref")
        if not detail_ref:
            return _http_error(400, "missing trace detail ref")
        data = build_webui_trace_detail_response(decoded_key, detail_ref, history=history)
        if data is None:
            return _http_error(404, "trace detail not found")
        return _http_json_response(
            data,
            accept_encoding=_combined_list_header(request.headers, "Accept-Encoding"),
            extra_headers=_NO_STORE_HEADERS,
        )
