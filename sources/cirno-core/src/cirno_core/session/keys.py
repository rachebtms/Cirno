"""Shared session key constants and helpers."""

from __future__ import annotations

HEARTBEAT_SESSION_KEY = "heartbeat"


def is_dream_session(key: str) -> bool:
    """Identify the per-run session namespace owned by Dream."""
    return key.startswith("dream:")


def is_internal_session(key: str) -> bool:
    """Identify maintenance sessions whose context is not a user conversation."""
    return key == HEARTBEAT_SESSION_KEY or is_dream_session(key)


def session_key_for_channel(channel: str, chat_id: str) -> str:
    """Return the session key for a channel/chat pair."""
    return f"{channel}:{chat_id}"



# Reserved identity within each instance; it never follows the display handle.
ROUTER_CHAT_ID = "b1ec9323-2155-5f24-bc56-1da2f59aeecb"
ROUTER_SESSION_KEY = session_key_for_channel("websocket", ROUTER_CHAT_ID)
