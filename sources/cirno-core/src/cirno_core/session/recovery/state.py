"""Conversation recovery state ownership."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session
from cirno_core.session.session_identity import webui_chat_id

from .contracts import (
    PENDING_FOLLOWUPS_KEY,
    PENDING_USER_TURN_KEY,
    RECOVERY_METADATA_KEY,
    RUNTIME_CHECKPOINT_KEY,
)

_RECOVERY_STATUSES = frozenset({"resuming", "awaiting_user", "recovered", "failed"})


def recovery_state_from_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return a sanitized recovery state suitable for the WebSocket wire."""
    value = metadata.get(RECOVERY_METADATA_KEY) if metadata else None
    if not isinstance(value, dict):
        return None
    state = cast(dict[str, Any], value)
    status = state.get("status")
    recovery_id = state.get("recovery_id")
    if status not in _RECOVERY_STATUSES or not isinstance(recovery_id, str):
        return None
    payload: dict[str, Any] = {"status": status, "recovery_id": recovery_id}
    reason = state.get("reason")
    if isinstance(reason, str) and reason:
        payload["reason"] = reason
    attempts = state.get("attempts")
    if isinstance(attempts, int) and attempts >= 0:
        payload["attempts"] = attempts
    can_continue = state.get("can_continue")
    if isinstance(can_continue, bool):
        payload["can_continue"] = can_continue
    failure_error_kind = state.get("failure_error_kind")
    if isinstance(failure_error_kind, str) and failure_error_kind in {
        "configuration",
        "authentication",
        "billing",
        "connection",
        "timeout",
        "rate_limit",
        "server",
        "unknown",
    }:
        payload["failure_error_kind"] = failure_error_kind
    if state.get("reply_preserved") is True:
        payload["reply_preserved"] = True
    return payload


def set_recovery_state(
    session: Session,
    *,
    status: str,
    recovery_id: str,
    attempts: int,
    reason: str,
    resume_message_count: int | None = None,
    can_continue: bool = True,
) -> dict[str, Any]:
    state = {
        "status": status,
        "recovery_id": recovery_id,
        "attempts": max(0, attempts),
        "reason": reason,
        "updated_at": datetime.now().isoformat(),
    }
    if not can_continue:
        state["can_continue"] = False
    if resume_message_count is not None:
        state["resume_message_count"] = max(0, resume_message_count)
    session.metadata[RECOVERY_METADATA_KEY] = state
    session.updated_at = datetime.now()
    return state


def resume_message_count(session: Session) -> int | None:
    raw_value = cast(object, session.metadata.get(RECOVERY_METADATA_KEY))
    value = cast(dict[str, Any], raw_value) if isinstance(raw_value, dict) else None
    if value is None:
        return None
    count = value.get("resume_message_count")
    return count if isinstance(count, int) and count >= 0 else None


def has_saved_continuation_context(session: Session) -> bool:
    """Whether an interrupted turn left model-visible context to continue from."""
    last_user = next(
        (
            index
            for index in range(len(session.messages) - 1, -1, -1)
            if session.messages[index].get("role") == "user"
        ),
        None,
    )
    if last_user is None:
        return False
    tail = session.messages[last_user + 1 :]
    return bool(tail) and (
        tail[-1].get("role") == "tool"
        or any(message.get("_recovery_interrupted") is True for message in tail)
        or any(
            message.get("role") == "assistant" and bool(message.get("tool_calls"))
            for message in tail
        )
    )


def needs_recovery(metadata: Mapping[str, Any]) -> bool:
    if metadata.get(PENDING_USER_TURN_KEY) is True:
        return True
    if isinstance(metadata.get(RUNTIME_CHECKPOINT_KEY), dict):
        return True
    followups = metadata.get(PENDING_FOLLOWUPS_KEY)
    if isinstance(followups, list) and len(cast(list[object], followups)) > 0:
        return True
    state = recovery_state_from_metadata(metadata)
    return bool(state and state["status"] in {"resuming", "awaiting_user", "failed"})


async def has_unfinished_transcript(sessions: SessionManager, session_key: str) -> bool:
    from cirno_core.session.transcript import has_unfinished_transcript_tail

    return await sessions.state.project_history(
        session_key,
        lambda history: has_unfinished_transcript_tail(session_key, history=history),
    )


def webui_route(session_key: str) -> tuple[str, str] | None:
    chat_id = webui_chat_id(session_key)
    return ("websocket", chat_id) if chat_id is not None else None
