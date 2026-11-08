"""Models ownership for WebUI session presentation."""

from __future__ import annotations

from cirno_core.agent.tools.context import current_request_context
from cirno_core.bus.outbound_events import (
    TurnModelUpdatedEvent,
    outbound_message_for_event,
)
from cirno_core.bus.queue import MessageBus
from cirno_core.providers.fallback_provider import FallbackModelObserver, FallbackModelSelection


def build_webui_fallback_model_observer(bus: MessageBus) -> FallbackModelObserver:
    """Translate provider fallback choices into chat-scoped WebUI events."""

    async def _publish(selection: FallbackModelSelection) -> None:
        context = current_request_context()
        if context is None or context.channel != "websocket":
            return
        chat_id = str(context.chat_id or "").strip()
        if not chat_id:
            return
        await bus.publish_outbound(
            outbound_message_for_event(
                channel=context.channel,
                chat_id=chat_id,
                event=TurnModelUpdatedEvent(
                    model=selection.model,
                    model_preset=(
                        context.runtime.model_preset if context.runtime is not None else None
                    ),
                    fallback=True,
                    reauth_provider=selection.reauth_provider,
                ),
                metadata=context.metadata,
            )
        )

    return _publish
