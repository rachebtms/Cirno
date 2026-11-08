"""Session privacy policy for execution diagnostics without loading a transcript."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cirno_core.session.model import Session
    from cirno_core.session.manager import SessionManager


def content_logging_allowed(sessions: SessionManager, key: str, *, session: Session | None = None, ephemeral: bool = False) -> bool:
    if ephemeral:
        return False
    snapshot = session or sessions.state.peek_header(key, include_runtime=False)
    return snapshot is not None and snapshot.policy.persist and snapshot.policy.log_content
