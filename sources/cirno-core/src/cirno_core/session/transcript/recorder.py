"""Recorder for durable conversation presentation."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from cirno_core.session.display_history import (
    HISTORY_GENERATION_METADATA_KEY,
)
from cirno_core.session.manager import SessionManager
from cirno_core.session.presentation_history import (
    fact_from_record,
)
from cirno_core.session.session_identity import webui_session_key
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.state import SessionOperationQueueFullError
from cirno_core.session.transport_metadata import (
    WEBUI_TURN_METADATA_KEY,
)
from loguru import logger

from .inputs import build_user_transcript_event
from .records import (
    _chat_id_from_session_key,
    _local_media_paths,
    _record_for_append,
    _response_sources,
    normalize_webui_turn_id,
    webui_message_source,
)


def append_transcript_object(
    session_key: str,
    obj: dict[str, Any],
    *,
    sessions: SessionManager,
) -> None:
    """Offline import/fixture helper; runtime writes through the async recorder."""
    sessions.append_history(session_key, [fact_from_record(_record_for_append(obj))])


async def append_session_message_input(
    session_key: str,
    *,
    sessions: SessionManager,
    content: str,
    created_at_ms: int,
    session_message: Mapping[str, Any],
    expected_generation: str | None = None,
    input_origin: Mapping[str, Any] | None = None,
) -> None:
    chat_id = _chat_id_from_session_key(session_key)
    if chat_id is None:
        return
    event = build_user_transcript_event(chat_id, content)
    if event is None:
        return
    event.update(created_at_ms=created_at_ms, session_message=dict(session_message))
    if input_origin is not None:
        event["input_origin"] = dict(input_origin)
    await sessions.state.append_history(
        session_key, [fact_from_record(event)], expected_generation=expected_generation
    )


class WebUITranscriptRecorder:
    """Capture channel facts through the session owner before transport fan-out."""

    def __init__(self, sessions: SessionManager | None, log: Any = logger) -> None:
        self.sessions = sessions
        self._log = log
        self._turn_sequences: dict[tuple[str, str], int] = {}

    def client_turn_metadata(self, value: Any) -> dict[str, str]:
        return {WEBUI_TURN_METADATA_KEY: normalize_webui_turn_id(value)}

    def prepare_event(
        self,
        chat_id: str,
        event: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        phase: str | None = None,
        include_source: bool = False,
    ) -> None:
        if include_source and (source := webui_message_source(metadata)):
            event["source"] = source
        if include_source and metadata is not None and "response_sources" in metadata:
            event["response_sources"] = _response_sources(metadata["response_sources"])
        self._annotate_turn(chat_id, event, metadata, phase)

    async def prepare_and_append(
        self,
        chat_id: str,
        event: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
        phase: str | None = None,
        include_source: bool = False,
        transcript_overrides: dict[str, Any] | None = None,
    ) -> bool:
        self.prepare_event(
            chat_id, event, metadata=metadata, phase=phase, include_source=include_source
        )
        record = {**event, **(transcript_overrides or {})}
        return await self.append(chat_id, record, metadata=metadata)

    async def prepare_and_append_stream_event(
        self,
        chat_id: str,
        event: dict[str, Any],
        *,
        completed_text: str | None,
        metadata: dict[str, Any] | None = None,
        phase: str | None = None,
        include_source: bool = False,
    ) -> bool:
        self.prepare_event(
            chat_id, event, metadata=metadata, phase=phase, include_source=include_source
        )
        if event.get("event") in {"delta", "reasoning_delta"}:
            return True
        record = dict(event)
        if completed_text is not None:
            record["text"] = completed_text
        return await self.append(chat_id, record, metadata=metadata)

    async def append_user_message(
        self,
        chat_id: str,
        text: str,
        *,
        metadata: dict[str, Any],
        media_paths: list[str] | None = None,
        cli_apps: list[dict[str, Any]] | None = None,
        mcp_presets: list[dict[str, Any]] | None = None,
        session_mentions: Sequence[Mapping[str, Any]] | None = None,
    ) -> bool:
        if text.strip() == "/stop" and not media_paths:
            return False
        event = build_user_transcript_event(
            chat_id,
            text,
            media_paths=media_paths,
            local_media_paths=_local_media_paths(metadata),
            cli_apps=cli_apps,
            mcp_presets=mcp_presets,
            session_mentions=session_mentions,
        )
        if event is None:
            return False
        return await self.prepare_and_append(chat_id, event, metadata=metadata, phase="user")

    async def append(
        self,
        chat_id: str,
        event: dict[str, Any],
        *,
        metadata: dict[str, Any] | None,
    ) -> bool:
        if self.sessions is None:
            return True  # A transport-only channel has no durable session service.
        generation = (metadata or {}).get(HISTORY_GENERATION_METADATA_KEY)
        if not isinstance(generation, str) or not generation:
            self._log.warning("history event has no admitted generation for {}", chat_id)
            return False
        try:
            fact = fact_from_record(_record_for_append(event))
            await self.sessions.state.append_history(
                webui_session_key(chat_id), [fact], expected_generation=generation
            )
        except (
            OSError,
            ValueError,
            TypeError,
            sqlite3.Error,
            SessionConflictError,
            SessionOperationQueueFullError,
        ) as exc:
            self._log.warning("history append failed for {}: {}", chat_id, exc)
            return False
        return True

    def _next_turn_seq(self, chat_id: str, turn_id: str) -> int:
        key = (chat_id, turn_id)
        sequence = self._turn_sequences.get(key, 0) + 1
        self._turn_sequences[key] = sequence
        return sequence

    def _annotate_turn(
        self,
        chat_id: str,
        event: dict[str, Any],
        metadata: dict[str, Any] | None,
        phase: str | None,
    ) -> None:
        turn_id = (metadata or {}).get(WEBUI_TURN_METADATA_KEY)
        if phase is None or not isinstance(turn_id, str) or not turn_id:
            return
        event.update(
            turn_id=turn_id, turn_phase=phase, turn_seq=self._next_turn_seq(chat_id, turn_id)
        )
        if phase == "complete":
            self._turn_sequences.pop((chat_id, turn_id), None)
