"""Create the personal Router independently of its transports and display name."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.roles import conversation_role

if TYPE_CHECKING:
    from cirno_core.session.manager import SessionManager


async def ensure_router_session(sessions: SessionManager, *, handle: str | None = None, initialize: bool = False) -> str:
    # Reopening an existing Router reads only the header, never its model checkpoint.
    await sessions.state.open_with_metadata(ROUTER_SESSION_KEY, {
        "role": conversation_role(ROUTER_SESSION_KEY).name, "webui": True,
    })
    snapshot = await sessions.state.read_metadata(ROUTER_SESSION_KEY, include_runtime=False)
    if snapshot is None:
        raise RuntimeError("Router session disappeared during initialization")
    metadata: dict[str, Any] = snapshot["metadata"]
    saved = metadata.get("session_handle")
    name = (handle if initialize else saved) or handle or saved or "cirno"
    if initialize or not saved or metadata.get("title") != f"@{name}":
        await sessions.state.rename_session_handle(ROUTER_SESSION_KEY, name)
    return ROUTER_SESSION_KEY
