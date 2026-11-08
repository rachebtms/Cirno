"""Activity ownership for WebUI session presentation."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from uuid import uuid4

from cirno_core.bus.events import InboundMessage
from cirno_core.bus.outbound_events import (
    GoalStatusEvent,
    outbound_message_for_event,
)
from cirno_core.bus.queue import MessageBus
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)

_WEBSOCKET_TURN_WALL_STARTED_AT: dict[str, float] = {}


_WEBSOCKET_TURN_IDS: dict[str, str] = {}


_WEBSOCKET_TURN_OWNERS: dict[str, str] = {}


@dataclass(frozen=True)
class _WebsocketTurn:
    started_at: float
    turn_id: str | None
    transcript_persistence_failed: bool = False


_WEBSOCKET_ACTIVE_TURNS: dict[str, dict[str, _WebsocketTurn]] = {}


def _sync_websocket_turn_projection(chat_id: str) -> None:
    turns = _WEBSOCKET_ACTIVE_TURNS.get(chat_id)
    if not turns:
        _WEBSOCKET_ACTIVE_TURNS.pop(chat_id, None)
        _WEBSOCKET_TURN_WALL_STARTED_AT.pop(chat_id, None)
        _WEBSOCKET_TURN_IDS.pop(chat_id, None)
        _WEBSOCKET_TURN_OWNERS.pop(chat_id, None)
        return

    owner = next(reversed(turns))
    turn = turns[owner]
    _WEBSOCKET_TURN_WALL_STARTED_AT[chat_id] = turn.started_at
    _WEBSOCKET_TURN_OWNERS[chat_id] = owner
    if turn.turn_id is None:
        _WEBSOCKET_TURN_IDS.pop(chat_id, None)
    else:
        _WEBSOCKET_TURN_IDS[chat_id] = turn.turn_id


def websocket_turn_wall_started_at(chat_id: str) -> float | None:
    """Return ``time.time()`` when the active user turn began, if still running."""
    return _WEBSOCKET_TURN_WALL_STARTED_AT.get(chat_id)


def websocket_turn_id(chat_id: str) -> str | None:
    """Return the WebUI identity of the active turn, when one was provided."""
    return _WEBSOCKET_TURN_IDS.get(chat_id)


def register_queued_websocket_turn_if_idle(
    chat_id: str,
    turn_id: str | None,
) -> str | None:
    """Track an accepted WebUI turn while it waits for AgentLoop admission."""
    if websocket_turn_wall_started_at(chat_id) is not None:
        return None
    owner = uuid4().hex
    _WEBSOCKET_ACTIVE_TURNS.setdefault(chat_id, {})[owner] = _WebsocketTurn(
        started_at=time.time(),
        turn_id=turn_id,
    )
    _sync_websocket_turn_projection(chat_id)
    return owner


def websocket_turn_owner_is_registered(
    chat_id: str,
    owner: str,
    turn_id: str | None,
) -> bool:
    """Return whether websocket ingress registered this owner for the turn."""
    turn = _WEBSOCKET_ACTIVE_TURNS.get(chat_id, {}).get(owner)
    return turn is not None and turn.turn_id == turn_id


def websocket_turn_transcript_persistence_failed(
    chat_id: str,
    owner: str | None = None,
) -> bool:
    """Return whether one active owner has an incomplete canonical transcript."""
    turns = _WEBSOCKET_ACTIVE_TURNS.get(chat_id)
    if not turns:
        return False
    selected_owner = owner or next(reversed(turns))
    turn = turns.get(selected_owner)
    return turn.transcript_persistence_failed if turn is not None else False


def mark_websocket_turn_transcript_persistence_failed(
    chat_id: str,
    owner: str | None,
) -> bool:
    """Keep a turn active when any canonical display event could not be written."""
    if not owner:
        return False
    turns = _WEBSOCKET_ACTIVE_TURNS.get(chat_id)
    if turns is None or owner not in turns:
        return False
    turns[owner] = replace(turns[owner], transcript_persistence_failed=True)
    return True


def clear_websocket_turn_if_current(
    chat_id: str,
    owner: str | None,
    *,
    preserve_persistence_failure: bool = False,
) -> bool:
    """Clear one lifecycle owner without disturbing concurrent turns for the chat."""
    if not owner:
        return False
    turns = _WEBSOCKET_ACTIVE_TURNS.get(chat_id)
    if turns is None or owner not in turns:
        return False
    if preserve_persistence_failure and turns[owner].transcript_persistence_failed:
        return False
    turns.pop(owner)
    _sync_websocket_turn_projection(chat_id)
    return True


def clear_websocket_turns(chat_id: str) -> None:
    """Forget every in-process turn projection for a discarded chat."""
    _WEBSOCKET_ACTIVE_TURNS.pop(chat_id, None)
    _sync_websocket_turn_projection(chat_id)


async def publish_turn_run_status(
    bus: MessageBus,
    msg: InboundMessage,
    status: str,
    *,
    started_at: float | None = None,
) -> None:
    """Notify WebSocket clients while a user turn is executing (timing strip)."""
    if msg.channel != "websocket":
        return
    cid = str(msg.chat_id)
    started_at_event: float | None = None
    if status == "running":
        if isinstance(started_at, int | float) and started_at > 0:
            t0 = float(started_at)
        else:
            t0 = time.time()
        started_at_event = t0
        owner = msg.metadata.get(WEBSOCKET_TURN_OWNER_METADATA_KEY)
        if not isinstance(owner, str) or not owner:
            owner = uuid4().hex
            msg.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] = owner
        turn_id = msg.metadata.get(WEBUI_TURN_METADATA_KEY)
        current_turn_id = turn_id if isinstance(turn_id, str) and turn_id else None
        turns = _WEBSOCKET_ACTIVE_TURNS.setdefault(cid, {})
        # Re-registration makes this owner the latest projection.
        turns.pop(owner, None)
        turns[owner] = _WebsocketTurn(started_at=t0, turn_id=current_turn_id)
        _sync_websocket_turn_projection(cid)
    await bus.publish_outbound(
        outbound_message_for_event(
            channel=msg.channel,
            chat_id=cid,
            event=GoalStatusEvent(status=status, started_at=started_at_event),
            metadata=msg.metadata,
        ),
    )
