"""Status for durable conversation presentation."""

from __future__ import annotations

from typing import Any

from cirno_core.session.display_history import (
    HistoryReader,
)
from cirno_core.session.presentation_history import (
    record_from_fact,
)

from .contracts import WEBUI_FORK_MARKER_EVENT, WEBUI_TRANSCRIPT_INCOMPLETE_KEY


def has_pending_tool_calls(
    lines: list[dict[str, Any]],
    *,
    active_turn_started_at: float | None = None,
    active_turn_id: str | None = None,
    active_turn_transcript_persistence_failed: bool = False,
) -> bool:
    """Return True when the selected transcript tail looks like an unfinished turn."""
    # An older canonical turn can remain unsafe even after a later turn
    # completes. Recovery removes this marker only after matching durable
    # session history, so no later turn_end may hide it.
    if any(rec.get(WEBUI_TRANSCRIPT_INCOMPLETE_KEY) is True for rec in lines):
        return True
    if active_turn_started_at is not None:
        if active_turn_transcript_persistence_failed:
            return True
        if active_turn_id is None:
            return True
        for rec in reversed(lines):
            transcript_turn_id = rec.get("turn_id")
            if not isinstance(transcript_turn_id, str) or not transcript_turn_id:
                continue
            if transcript_turn_id != active_turn_id:
                return True
            return rec.get("event") != "turn_end"
        return True

    for rec in reversed(lines):
        ev = rec.get("event")
        if ev == "turn_end":
            return False
        if ev == "user":
            return False
        if ev == "message":
            return rec.get("kind") in {"tool_hint", "progress", "reasoning"}
        if ev in {
            "delta",
            "stream_end",
            "reasoning_delta",
            "reasoning_end",
            "file_edit",
        }:
            return True
        if ev in {WEBUI_FORK_MARKER_EVENT}:
            continue
    return False


def has_unfinished_transcript_tail(session_key: str, *, history: HistoryReader) -> bool:
    return has_pending_tool_calls(
        [record_from_fact(fact, session_key) for fact in history.pending_tail_facts()]
    )


def completed_turn_ids(lines: list[dict[str, Any]]) -> list[str]:
    """Return stable identities for turns with an explicitly persisted completion."""
    completed: list[str] = []
    seen: set[str] = set()
    for rec in lines:
        if rec.get("event") != "turn_end" or rec.get(WEBUI_TRANSCRIPT_INCOMPLETE_KEY) is True:
            continue
        turn_id = rec.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id or turn_id in seen:
            continue
        seen.add(turn_id)
        completed.append(turn_id)
    return completed
