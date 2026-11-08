"""Thread for durable conversation presentation."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, cast

from cirno_core.session.display_history import (
    HistoryReader,
)
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.session.model import Session
from cirno_core.session.outbound_wire import project_tool_events

from .activity import _normalize_tool_events, tool_trace_lines_from_events
from .contracts import (
    WEBUI_REPLAY_IDENTITY_KEY,
    WEBUI_TRANSCRIPT_SCHEMA_VERSION,
    TranscriptReplayStats,
    SessionBackfillTurn,
)
from .event_projection import _client_projection_event
from .identities import _ensure_replay_identities, _history_generation, _split_transcript_turns
from .inputs import _session_assistant_event, session_backfill_turns, _session_user_event
from .paging import _select_transcript_page
from .prompts import prompt_view_snapshot
from .recovery import (
    _needs_incomplete_turn_recovery,
    _needs_user_event_backfill,
    _recover_incomplete_turns,
    _with_backfilled_user,
)
from .status import completed_turn_ids, has_pending_tool_calls
from .traces import _client_projection_events


def build_session_thread_response(
    session: Session,
    *,
    active: bool = False,
    latency_ms: int | None = None,
    augment_user_media: Callable[[list[str], list[str]], list[dict[str, Any]]] | None = None,
    augment_assistant_media: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    augment_assistant_text: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Project a Session snapshot without creating a second display transcript."""
    rows: list[dict[str, Any]] = []
    chat_id = session.key.split(":", 1)[-1]
    turn_id = f"session:{session.key}:0"
    created_at_ms = int(session.created_at.timestamp() * 1000)
    for index, message in enumerate(session.messages):
        if is_hidden_history_message(message):
            continue
        if message.get("role") == "user":
            turn_id = f"session:{session.key}:{index}"
        timestamp = message.get("timestamp")
        if isinstance(timestamp, str):
            try:
                created_at_ms = int(datetime.fromisoformat(timestamp).timestamp() * 1000)
            except ValueError:
                pass
        records: list[dict[str, Any]] = []
        row = _session_user_event(session.key, message) or _session_assistant_event(
            session.key, message
        )
        reasoning = message.get("reasoning_content")
        if message.get("role") == "assistant" and isinstance(reasoning, str) and reasoning:
            records.append({"event": "message", "text": reasoning, "kind": "reasoning"})
        calls = message.get("tool_calls")
        has_calls = isinstance(calls, list) and len(cast(list[object], calls)) > 0
        if row is not None and has_calls:
            row["kind"] = "progress"
            records.append(row)
        if message.get("role") == "assistant":
            tools = project_tool_events(_normalize_tool_events(message.get("tool_events")))
            if tools:
                records.append(
                    {
                        "event": "message",
                        "kind": "tool_hint",
                        "text": "\n".join(tool_trace_lines_from_events(tools)),
                        "tool_events": tools,
                    }
                )
            edits = message.get("file_edit_events")
            if isinstance(edits, list) and edits:
                records.append({"event": "file_edit", "edits": edits})
        if row is not None and not has_calls:
            records.append(row)
        for offset, record in enumerate(records):
            record.update(
                {
                    "chat_id": chat_id,
                    "turn_id": turn_id,
                    "turn_phase": "user"
                    if record["event"] == "user"
                    else "reasoning"
                    if record.get("kind") == "reasoning"
                    else "activity"
                    if record["event"] == "file_edit"
                    or record.get("kind") in {"progress", "tool_hint"}
                    else "answer",
                    "created_at_ms": created_at_ms,
                    WEBUI_REPLAY_IDENTITY_KEY: f"session:{session.key}:{index}:{offset}",
                }
            )
            rows.append(record)
    if not active and rows:
        rows.append(
            {
                "event": "turn_end",
                "chat_id": chat_id,
                "turn_id": turn_id,
                "latency_ms": latency_ms,
                WEBUI_REPLAY_IDENTITY_KEY: f"session:{session.key}:end",
            }
        )
    events = [
        event
        for record in rows
        if (
            event := _client_projection_event(
                record,
                augment_user_media=augment_user_media,
                augment_assistant_media=augment_assistant_media,
                augment_assistant_text=augment_assistant_text,
            )
        )
        is not None
    ]
    return {
        "schemaVersion": WEBUI_TRANSCRIPT_SCHEMA_VERSION,
        "sessionKey": session.key,
        "projection": "events",
        "events": events,
        "active_turn_id": turn_id if active else None,
    }


def build_webui_thread_response(
    session_key: str,
    *,
    history: HistoryReader,
    augment_user_media: Callable[[list[str], list[str]], list[dict[str, Any]]] | None = None,
    augment_assistant_media: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    augment_assistant_text: Callable[[str], str] | None = None,
    session_messages: list[dict[str, Any]] | None = None,
    session_messages_loader: Callable[[], list[dict[str, Any]] | None] | None = None,
    session_version_loader: Callable[[], tuple[str, int] | None] | None = None,
    active_turn_started_at: float | None = None,
    active_turn_id: str | None = None,
    active_turn_transcript_persistence_failed: bool = False,
    limit: int | None = None,
    direction: str | None = None,
    before: str | None = None,
    after: str | None = None,
    stats: TranscriptReplayStats | None = None,
) -> dict[str, Any] | None:
    """Return canonical transcript events for the WebUI projector."""
    replay_stats = stats or TranscriptReplayStats()
    lines, page = _select_transcript_page(
        history=history,
        limit=limit,
        before=before,
        after=after,
        stats=replay_stats,
    )
    if not lines and active_turn_started_at is None:
        return None
    session_turns: list[SessionBackfillTurn] | None = None

    def load_session_turns() -> list[SessionBackfillTurn]:
        nonlocal session_messages, session_turns
        if session_turns is None:
            if session_messages is None and session_messages_loader is not None:
                session_messages = session_messages_loader()
            session_turns = session_backfill_turns(session_key, session_messages or [])
        return session_turns

    if _needs_user_event_backfill(lines):
        view, _ = prompt_view_snapshot(
            session_key,
            history=history,
            session_turns_loader=load_session_turns,
            session_version_loader=session_version_loader,
        )
        recovered_lines: list[dict[str, Any]] = []
        selected_turns = _split_transcript_turns(lines)
        for turn in selected_turns:
            # Page selection assigns this absolute identity before any recovery.
            ordinal = int(turn[0][WEBUI_REPLAY_IDENTITY_KEY].split(":")[1])
            user = view.backfilled_users.get(ordinal)
            recovered_lines.extend(_with_backfilled_user(turn, user) if user is not None else turn)
        lines = recovered_lines
    if _needs_incomplete_turn_recovery(lines):
        lines = _recover_incomplete_turns(lines, load_session_turns())
    lines = _ensure_replay_identities(lines)
    payload: dict[str, Any] = {
        "schemaVersion": WEBUI_TRANSCRIPT_SCHEMA_VERSION,
        "sessionKey": session_key,
        "completed_turn_ids": completed_turn_ids(lines),
        "has_pending_tool_calls": has_pending_tool_calls(
            lines,
            active_turn_started_at=active_turn_started_at,
            active_turn_id=active_turn_id,
            active_turn_transcript_persistence_failed=(active_turn_transcript_persistence_failed),
        ),
        "active_turn_id": active_turn_id,
    }
    replay_started = time.perf_counter()
    events, fork_boundary_event_index = _client_projection_events(
        lines,
        history_generation=_history_generation(history),
        augment_user_media=augment_user_media,
        augment_assistant_media=augment_assistant_media,
        augment_assistant_text=augment_assistant_text,
    )
    replay_stats.replay_ms += int((time.perf_counter() - replay_started) * 1000)
    payload["projection"] = "events"
    payload["events"] = events
    page["loaded_event_count"] = len(events)
    if fork_boundary_event_index is not None:
        payload["fork_boundary_event_index"] = fork_boundary_event_index
    payload["page"] = page
    return payload
