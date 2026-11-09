"""Periodic instructions routed into the Router conversation."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from cirno_core.bus.events import InboundMessage
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY, PENDING_FOLLOWUPS_KEY
from cirno_core.session.router_session import ensure_router_session

if TYPE_CHECKING:
    from cirno_core.bus.queue import MessageBus
    from cirno_core.session.manager import SessionManager


async def enqueue_heartbeat(sessions: SessionManager, bus: MessageBus, content: str) -> bool:
    key = await ensure_router_session(sessions)
    header = await sessions.state.read_metadata(key)
    assert header is not None, "The Router must exist after session admission"
    if header["metadata"].get("heartbeat_paused", False):
        return False
    if any(
        row.get("metadata", {}).get("_heartbeat")
        for row in header["metadata"].get(PENDING_FOLLOWUPS_KEY, [])
    ):
        return False
    message = InboundMessage(
        channel="system",
        sender_id="heartbeat",
        chat_id=key,
        session_key_override=key,
        input_role="system",
        require_existing_session=True,
        content="Heartbeat: review these periodic instructions and relevant active work. Use user__message only if the user needs an update.\n\n"
        + content,
        metadata={"_heartbeat": True},
    )
    identifier = await sessions.state.queue_followup(key, message)
    message = replace(message, metadata={**message.metadata, PENDING_FOLLOWUP_ID_KEY: identifier})
    await bus.publish_inbound(message)
    return True


async def heartbeat_paused(sessions: SessionManager) -> bool:
    from cirno_core.session.keys import ROUTER_SESSION_KEY
    header = await sessions.state.read_metadata(ROUTER_SESSION_KEY, include_runtime=False)
    return bool(header and header["metadata"].get("heartbeat_paused", False))


async def discard_paused_heartbeat(sessions: SessionManager, message: InboundMessage) -> bool:
    """Retire queued heartbeats without touching user turns or other follow-ups."""
    if not message.metadata.get("_heartbeat") or not await heartbeat_paused(sessions):
        return False
    identifier = message.metadata.get(PENDING_FOLLOWUP_ID_KEY)
    if isinstance(identifier, str) and identifier:
        await sessions.state.acknowledge_followups(message.session_key, [identifier])
    return True


def has_active_tasks(content: str) -> bool:
    """True if HEARTBEAT.md has task lines, ignoring headers, blanks and comments."""
    in_comment = False
    in_active_section: bool = False
    for line in content.splitlines():
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if not stripped or stripped.startswith("#"):
            if stripped.startswith("##") and not stripped.startswith("###"):
                heading = stripped.lstrip("#").strip().lower()
                in_active_section = heading.startswith("active tasks")
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped[4:]:
                in_comment = True
            continue
        if in_active_section is False:
            continue
        return True
    return False
