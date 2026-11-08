"""Admit user-visible messages, persist their history and enqueue channel delivery."""

import asyncio
from dataclasses import replace
from typing import Any, cast

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.session.keys import ROUTER_SESSION_KEY, session_key_for_channel
from cirno_core.session.manager import SessionManager


async def publish_to_channel(
    msg: OutboundMessage,
    *,
    bus: MessageBus,
    session_manager: SessionManager,
    record: bool = False,
    session_key: str | None = None,
    session_generation: str | None = None,
) -> None:
    """Publish a user-visible message and mirror it into its admitted session."""
    metadata = dict(msg.metadata or {})
    record = record or bool(metadata.pop("_record_channel_delivery", False))
    raw_key = metadata.pop("_session_key", None)
    raw_generation = metadata.pop("_session_generation", None)
    expected_generation = (
        session_generation
        if session_generation is not None
        else raw_generation
        if isinstance(raw_generation, str)
        else None
    )
    key = session_key or (raw_key if isinstance(raw_key, str) else None)
    if key is None:
        key = session_key_for_channel(msg.channel, msg.chat_id)
    if msg.channel == "websocket":
        from cirno_core.agent.turn_delivery import TurnRoute
        from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
        from cirno_core.session.session_identity import webui_session_key
        from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy

        route = await WebuiTurnRoutePolicy(session_manager).admit(
            TurnRoute(msg.channel, msg.chat_id, metadata),
            key,
            expected_generation,
        )
        metadata = route.metadata
        if key == webui_session_key(msg.chat_id):
            expected_generation = cast(str, metadata[HISTORY_GENERATION_METADATA_KEY])
    if metadata != (msg.metadata or {}):
        msg = replace(msg, metadata=metadata)
    if record and msg.channel != "cli" and (msg.content.strip() or msg.media):
        if expected_generation is None:
            # Cross-target sends admit their target before recording; subsequent
            # deletion or reset must still revoke this delivery's generation.
            target = await session_manager.state.get_header(key)
            expected_generation = target.generation
        extra: dict[str, Any] = {"_channel_delivery": True}
        if isinstance(metadata.get("_agent_ui"), dict):
            extra["agent_ui"] = dict(metadata["_agent_ui"])
        if msg.media:
            extra["media"] = list(msg.media)
        await session_manager.state.record_delivery(
            key,
            msg.content,
            extra,
            expected_generation=expected_generation,
        )
    await bus.publish_outbound(msg)
    if (
        record
        and key == ROUTER_SESSION_KEY
        and msg.channel == "websocket"
        and not metadata.get("_agent_ui")
    ):
        from cirno_server.channels.telegram.binding import TelegramBinding

        binding = await asyncio.to_thread(TelegramBinding().destination, "router")
        if binding is not None:
            await bus.publish_outbound(
                replace(
                    msg,
                    channel="telegram",
                    chat_id=binding["chat_id"],
                    delivery=None,
                    delivery_id=None,
                    metadata={
                        **{k: v for k, v in metadata.items() if k != "_telegram_reply_to"},
                        "_telegram_binding": binding["id"],
                        "_telegram_category": "router",
                    },
                )
            )
