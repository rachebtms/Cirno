"""Shared context prefix projection for rewinds and portable conversation forks."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from cirno_core.runtime.context import public_history_message
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.session.model import Session
from cirno_core.session.roles import conversation_role
from cirno_core.session.types import PARENT_SESSION_KEY, SESSION_TYPE_KEY

_FORK_VOLATILE_METADATA_KEYS = {
    "_stopped_at_iteration_limit",
    PARENT_SESSION_KEY,
    SESSION_TYPE_KEY,
    "goal_state",
    "work_report",
    "work_report_pending",
    "delegation_source",
    "delegated_by",
    "supervision_events",
    "pending_user_turn",
    "pending_user_followups",
    "runtime_checkpoint",
    "session_handle",
    "webui_recovery",
    "thread_goal",
    "title",
    "title_user_edited",
}


def session_prefix(source: Session, target_key: str, before_user_index: int) -> Session | None:
    """Project a fresh generation ending before the requested visible user input."""
    if before_user_index < 0:
        return None
    copied: list[dict[str, Any]] = []
    user_index = 0
    found_target = False
    for message in source.messages:
        if message.get("role") == "user" and not is_hidden_history_message(message):
            if user_index == before_user_index:
                found_target = True
                break
            user_index += 1
        copied.append(public_history_message(message))
    if user_index == before_user_index:
        found_target = True
    if not found_target:
        return None

    metadata = deepcopy(source.metadata)
    for key in _FORK_VOLATILE_METADATA_KEYS:
        metadata.pop(key, None)

    last_archived = min(source.last_archived, len(copied))
    if source.last_archived > len(copied):
        metadata.pop("_last_summary", None)
        last_archived = 0

    now = datetime.now()
    target = Session(
        key=target_key,
        messages=copied,
        created_at=now,
        updated_at=now,
        metadata=metadata,
        last_archived=last_archived,
        policy=source.policy,
    )
    return target


def fork_session(source: Session, target_key: str, before_user_index: int) -> Session | None:
    """Apply public Fork eligibility before projecting a portable context prefix."""
    if not conversation_role(source.key).can_fork:
        return None
    return session_prefix(source, target_key, before_user_index)
