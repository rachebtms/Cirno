"""Periodic instructions routed into the Cirno conversation."""

from dataclasses import replace

from cirno.bus.events import InboundMessage
from cirno.session.recovery import PENDING_FOLLOWUP_ID_KEY, PENDING_FOLLOWUPS_KEY
from cirno.webui.instance_api import ensure_global_session


async def enqueue_heartbeat(sessions, bus, content: str) -> bool:
    key = await ensure_global_session(sessions)
    header = await sessions.state.read_metadata(key)
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
