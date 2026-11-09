"""Conversation recovery delivery ownership."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Mapping
from typing import Any, cast

from cirno_core.bus.events import InboundMessage
from cirno_core.bus.outbound_events import (
    RecoveryStateEvent,
    SessionUpdatedEvent,
    outbound_message_for_event,
)
from cirno_core.bus.queue import MessageBus
from cirno_core.config.agents import ResumeConfig
from cirno_core.session import turn_continuation
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session
from cirno_core.session.session_identity import webui_session_key
from cirno_core.session.transport_metadata import WEBUI_TURN_METADATA_KEY

from .contracts import (
    RECOVERY_INBOUND_METADATA_KEY,
    REQUEST_ORIGIN_METADATA_KEY,
    request_origin_from_metadata,
)
from .pending import pending_followups


@dataclasses.dataclass(slots=True)
class RecoveryDelivery:
    sessions: SessionManager
    bus: MessageBus
    resume_settings: ResumeConfig

    async def publish(
        self,
        chat_id: str,
        state: Mapping[str, Any],
        *,
        generation: str,
    ) -> None:
        """Publish the recovery state and invalidate its sidebar projection."""
        metadata = {
            "_session_key": webui_session_key(chat_id),
            HISTORY_GENERATION_METADATA_KEY: generation,
        }
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel="websocket",
                chat_id=chat_id,
                event=RecoveryStateEvent(
                    status=cast(str, state["status"]),
                    recovery_id=cast(str, state["recovery_id"]),
                    reason=cast(str | None, state.get("reason")),
                    attempts=cast(int, state.get("attempts", 0)),
                    can_continue=cast(bool | None, state.get("can_continue")),
                    failure_error_kind=cast(str | None, state.get("failure_error_kind")),
                    reply_preserved=cast(bool | None, state.get("reply_preserved")),
                ),
                metadata=metadata,
            )
        )
        await self.bus.publish_outbound(
            outbound_message_for_event(
                channel="websocket",
                chat_id=chat_id,
                event=SessionUpdatedEvent(scope="thread"),
                metadata=metadata,
            )
        )

    async def queue_continuation(
        self,
        session: Session,
        chat_id: str,
        state: Mapping[str, Any],
    ) -> None:
        recovery_id = cast(str, state["recovery_id"])
        origin = request_origin_from_metadata(session.metadata)
        await self.bus.publish_inbound(
            InboundMessage(
                channel="websocket",
                sender_id="system:recovery",
                chat_id=chat_id,
                content=self.resume_settings.message,
                metadata={
                    "webui": True,
                    "_wants_stream": True,
                    WEBUI_TURN_METADATA_KEY: f"recovery:{recovery_id}",
                    RECOVERY_INBOUND_METADATA_KEY: recovery_id,
                    "_show_continuation_input": self.resume_settings.show_message,
                    turn_continuation.INTERNAL_CONTINUATION_META: True,
                    turn_continuation.SKIP_USER_PERSIST_META: True,
                    **({REQUEST_ORIGIN_METADATA_KEY: origin} if origin is not None else {}),
                },
                session_key_override=session.key,
                require_existing_session=True,
                session_generation=session.generation,
            )
        )

    async def requeue_pending_followups(self, session: Session) -> None:
        """Return durable live-turn follow-ups to the bus after a restart."""
        from cirno_core.profiles.awakening import awakening_prompt
        from cirno_core.session.keys import ROUTER_SESSION_KEY

        for message in pending_followups(session):
            if (session.key == ROUTER_SESSION_KEY and message.sender_id == "system:awakening"
                and message.metadata.get("_awakening") is True
                and not await asyncio.to_thread(awakening_prompt)):
                # Older releases retained this journal after completing introductions.
                identifier = await self.sessions.state.queue_followup(session.key, message)
                if identifier is not None:
                    await self.sessions.state.acknowledge_followups(session.key, [identifier])
                continue
            await self.bus.publish_inbound(message)
