"""Conversation recovery interruption ownership."""

from __future__ import annotations

from datetime import datetime

from cirno_core.session.model import Session

from .contracts import PENDING_USER_TURN_KEY


def restore_pending_interruption(session: Session, *, superseded: bool = False) -> bool:
    """Close a persisted user-only turn without pretending it was answered."""
    if not session.metadata.get(PENDING_USER_TURN_KEY):
        return False
    if session.messages and session.messages[-1].get("role") == "user":
        content = (
            "Task recovery was superseded by a newer message."
            if superseded
            else "Error: Task interrupted before a response was generated."
        )
        session.messages.append(
            {
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "_recovery_interrupted": True,
            }
        )
        session.provider_state = None
        session.updated_at = datetime.now()
    session.metadata.pop(PENDING_USER_TURN_KEY, None)
    return True


def append_recovery_interruption(session: Session, *, superseded: bool = False) -> None:
    """Close a restored partial turn whose last durable row is not the user message."""
    if session.messages and session.messages[-1].get("_recovery_interrupted") is True:
        return
    session.messages.append(
        {
            "role": "assistant",
            "content": (
                "Task recovery was superseded by a newer message."
                if superseded
                else "Error: Task recovery was interrupted before completion."
            ),
            "timestamp": datetime.now().isoformat(),
            "_recovery_interrupted": True,
        }
    )
    session.provider_state = None
    session.updated_at = datetime.now()
