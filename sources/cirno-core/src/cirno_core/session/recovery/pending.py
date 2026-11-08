"""Conversation recovery pending ownership."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from cirno_core.bus.events import InboundMessage
from cirno_core.session.model import Session

from .contracts import PENDING_FOLLOWUP_ID_KEY, PENDING_FOLLOWUPS_KEY


def record_pending_followup(session: Session, message: InboundMessage) -> str | None:
    """Durably journal a WebUI follow-up before injecting it into a live turn."""
    if (
        message.channel != "websocket"
        and not message.metadata.get("_session_message")
        and not message.metadata.get("_heartbeat")
    ):
        return None
    # Acknowledgement requires a replayable journal entry. Serialization failure
    # must reject admission before the input can be injected into a live turn.
    metadata = cast(dict[str, Any], json.loads(json.dumps(message.metadata)))
    existing_id = metadata.pop(PENDING_FOLLOWUP_ID_KEY, None)
    followup_id = existing_id if isinstance(existing_id, str) and existing_id else uuid4().hex
    records = _pending_followup_records(session)
    if any(record.get("id") == followup_id for record in records):
        return followup_id
    records.append(
        {
            "id": followup_id,
            "sender_id": message.sender_id,
            "channel": message.channel,
            "input_role": message.input_role,
            "chat_id": message.chat_id,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "media": list(message.media or []),
            "metadata": metadata,
        }
    )
    # This journal is the recovery source of truth, not a mirror of the
    # bounded in-memory injection queue.  A queued turn can receive more
    # follow-ups than the live queue accepts; dropping older journal entries
    # would make those acknowledged user messages unrecoverable after a
    # gateway restart.  Entries are removed only once their user rows are
    # committed by ``acknowledge_pending_followups``.
    session.metadata[PENDING_FOLLOWUPS_KEY] = records
    session.updated_at = datetime.now()
    return followup_id


def pending_followups(session: Session) -> list[InboundMessage]:
    """Decode still-unacknowledged follow-ups from durable session metadata."""
    messages: list[InboundMessage] = []
    for record in _pending_followup_records(session):
        followup_id = cast(object, record.get("id"))
        sender_id = cast(object, record.get("sender_id"))
        chat_id = cast(object, record.get("chat_id"))
        content = cast(object, record.get("content"))
        metadata = cast(object, record.get("metadata"))
        if (
            not isinstance(followup_id, str)
            or not followup_id
            or not isinstance(sender_id, str)
            or not sender_id
            or not isinstance(chat_id, str)
            or not chat_id
        ):
            continue
        if not isinstance(content, str) or not isinstance(metadata, dict):
            continue
        media_value = cast(object, record.get("media"))
        media = (
            [item for item in cast(list[object], media_value) if isinstance(item, str)]
            if isinstance(media_value, list)
            else []
        )
        timestamp = record.get("timestamp")
        # Older journals did not retain admission time; retain their existing recovery policy.
        received_at = (
            datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else datetime.now()
        )
        messages.append(
            InboundMessage(
                channel=record.get("channel", "websocket"),
                input_role=record.get("input_role"),
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                timestamp=received_at,
                media=media,
                metadata={**cast(dict[str, Any], metadata), PENDING_FOLLOWUP_ID_KEY: followup_id},
                session_key_override=session.key,
                require_existing_session=True,
                session_generation=session.generation,
            )
        )
    return messages


def acknowledge_pending_followups(session: Session, followup_ids: Iterable[str]) -> None:
    """Remove journal entries whose user rows were committed to history."""
    acknowledged = set(followup_ids)
    if not acknowledged:
        return
    records = [
        record
        for record in _pending_followup_records(session)
        if record.get("id") not in acknowledged
    ]
    if records:
        session.metadata[PENDING_FOLLOWUPS_KEY] = records
    else:
        session.metadata.pop(PENDING_FOLLOWUPS_KEY, None)


def _pending_followup_records(session: Session) -> list[dict[str, Any]]:
    raw = cast(object, session.metadata.get(PENDING_FOLLOWUPS_KEY))
    if not isinstance(raw, list):
        return []
    values = cast(list[object], raw)
    return [cast(dict[str, Any], value) for value in values if isinstance(value, dict)]
