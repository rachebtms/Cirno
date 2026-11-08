"""Routing ownership for WebUI session presentation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from cirno_core.agent.turn_delivery import TurnRoute
from cirno_core.bus.events import InboundMessage
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_identity import webui_session_key
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)

from .activity import websocket_turn_owner_is_registered
from .contracts import WEBUI_SESSION_METADATA_KEY


@dataclass(frozen=True)
class WebuiTurnRoutePolicy:
    """Expose independently dispatched agent turns to WebUI sessions."""

    sessions: SessionManager

    async def __call__(
        self,
        msg: InboundMessage,
        session_key: str,
        route: TurnRoute,
    ) -> TurnRoute:
        """Make an independently dispatched agent turn visible in WebUI."""
        routed = route
        if msg.channel == "telegram" and session_key == ROUTER_SESSION_KEY:
            # Telegram is another private entrance to the same personal agent.
            # Keep model activity on Cirno; only explicit replies go back to Telegram.
            metadata = dict(route.metadata)
            metadata.update(
                {
                    WEBUI_SESSION_METADATA_KEY: True,
                    "_wants_stream": True,
                    WEBUI_TURN_METADATA_KEY: metadata.get(WEBUI_TURN_METADATA_KEY)
                    or f"telegram:{uuid4().hex}",
                    "_telegram_reply_to": msg.chat_id,
                }
            )
            routed = TurnRoute("websocket", ROUTER_CHAT_ID, metadata, publish_lifecycle=True)
        internal_user_input = msg.channel == "system" and msg.is_user_input
        if (
            (
                msg.channel == "system"
                and msg.sender_id == "subagent"
                and msg.metadata.get("injected_event") == "subagent_result"
            )
            or internal_user_input
            or msg.metadata.get("_heartbeat") is True
            or msg.metadata.get("_awakening") is True
            or msg.metadata.get("_internal_continuation") is True
        ) and route.channel == "websocket":
            visible = session_key == ROUTER_SESSION_KEY
            if not visible:
                stored = await self.sessions.state.read_metadata(
                    session_key, include_runtime=False
                )
                visible = (
                    stored is not None
                    and stored["metadata"].get(WEBUI_SESSION_METADATA_KEY) is True
                )
            if visible:
                metadata = dict(route.metadata)
                turn_prefix = "session-input" if internal_user_input else "subagent"
                metadata.update(
                    {
                        WEBUI_SESSION_METADATA_KEY: True,
                        "_wants_stream": True,
                        WEBUI_TURN_METADATA_KEY: f"{turn_prefix}:{uuid4().hex}",
                    }
                )
                routed = replace(route, metadata=metadata, publish_lifecycle=True)

        if routed.channel == "websocket" and routed.publish_lifecycle:
            metadata = dict(routed.metadata)
            turn_id = metadata.get(WEBUI_TURN_METADATA_KEY)
            current_turn_id = turn_id if isinstance(turn_id, str) and turn_id else None
            queued_owner = metadata.get(WEBSOCKET_TURN_OWNER_METADATA_KEY)
            owner = (
                queued_owner
                if (
                    msg.channel == "websocket"
                    and isinstance(queued_owner, str)
                    and websocket_turn_owner_is_registered(
                        str(msg.chat_id),
                        queued_owner,
                        current_turn_id,
                    )
                )
                else uuid4().hex
            )
            metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] = owner
            routed = replace(routed, metadata=metadata, turn_id=current_turn_id)
            # Direct websocket turns publish their final idle transition from
            # the original input message. Carry the same server-owned identity
            # there, overwriting any untrusted client-supplied value.
            if msg.channel == "websocket":
                msg.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] = owner

        return routed

    async def admit(self, route: TurnRoute, session_key: str, generation: str | None) -> TurnRoute:
        """Bind replies to the display destination's admitted lifetime."""
        if route.channel != "websocket":
            return route
        target_key = webui_session_key(route.chat_id)
        metadata = dict(route.metadata)
        if target_key == session_key and generation is not None:
            metadata.setdefault(HISTORY_GENERATION_METADATA_KEY, generation)
            return replace(route, metadata=metadata)
        revision = await self.sessions.state.project_history(
            target_key, lambda history: history.revision
        )
        if revision is None:
            raise SessionConflictError("display destination is no longer active")
        admitted = metadata.get(HISTORY_GENERATION_METADATA_KEY)
        # A distinct alias admitted by the WebSocket edge must still be current.
        if admitted not in (None, generation, revision[0]):
            raise SessionConflictError("display destination generation was replaced")
        metadata[HISTORY_GENERATION_METADATA_KEY] = revision[0]
        return replace(route, metadata=metadata)
