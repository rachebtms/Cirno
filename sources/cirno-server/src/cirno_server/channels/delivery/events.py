"""Translate typed outbound events through the common channel interface."""

from __future__ import annotations

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import (
    ProgressEvent,
    StreamDeltaEvent,
    StreamEndEvent,
    StreamedResponseEvent,
)
from cirno_server.channels.base import BaseChannel


async def send_event(channel: BaseChannel, message: OutboundMessage) -> None:
    """Submit one event; admission, retry and delivery receipts belong to the caller."""
    event = message.event
    match event:
        case ProgressEvent(reasoning_end=True):
            await channel.send_reasoning_end(
                message.chat_id,
                message.metadata,
                stream_id=event.stream_id,
            )
        case ProgressEvent(reasoning_delta=True):
            await channel.send_reasoning_delta(
                message.chat_id,
                message.content,
                message.metadata,
                stream_id=event.stream_id,
            )
        case ProgressEvent() if event.reasoning:
            await channel.send_reasoning(message)
        case ProgressEvent() if event.file_edit_events:
            await channel.send_file_edit_events(
                message.chat_id, event.file_edit_events, message.metadata
            )
        case StreamDeltaEvent() | StreamEndEvent():
            await channel.send_delta(
                message.chat_id,
                message.content,
                message.metadata,
                stream_id=event.stream_id,
                stream_end=isinstance(event, StreamEndEvent),
                resuming=event.resuming if isinstance(event, StreamEndEvent) else False,
                merge_next=event.merge_next if isinstance(event, StreamEndEvent) else False,
            )
        case StreamedResponseEvent():
            pass  # Completion marker: the stream has already delivered its text.
        case _:
            await channel.send(message)
