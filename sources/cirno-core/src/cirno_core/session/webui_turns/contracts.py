"""Contracts ownership for WebUI session presentation."""

from __future__ import annotations

from typing import Any

from cirno_core.session.model import Session

WEBUI_SESSION_METADATA_KEY = "webui"


def mark_webui_session(session: Session, metadata: dict[str, Any]) -> bool:
    """Persist a WebUI marker only when the inbound websocket frame opted in."""
    if metadata.get(WEBUI_SESSION_METADATA_KEY) is not True:
        return False
    session.metadata[WEBUI_SESSION_METADATA_KEY] = True
    return True
