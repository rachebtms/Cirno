"""Coalesce consecutive deltas without crossing source, destination or stream boundaries."""

from __future__ import annotations

import asyncio

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import StreamDeltaEvent, StreamEndEvent, replace_outbound_event


def coalesce_stream_deltas(
    queue: asyncio.Queue[OutboundMessage], first_msg: OutboundMessage
) -> tuple[OutboundMessage, list[OutboundMessage]]:
    """Merge consecutive stream deltas for the same (channel, chat_id, stream_id).

    Metadata is part of the stream boundary: a resumed or rewritten turn must
    retain its own provenance. Return the first boundary for later dispatch.
    """
    first_event = first_msg.event
    assert isinstance(first_event, StreamDeltaEvent)
    first_stream_id = first_event.stream_id
    target_key = (first_msg.channel, first_msg.chat_id, first_stream_id)
    content = [first_msg.content]
    final_event: StreamDeltaEvent | StreamEndEvent = first_event
    non_matching: list[OutboundMessage] = []

    # Only merge consecutive deltas. As soon as we hit any other message,
    # stop and hand that boundary back to the dispatcher via `pending`.
    while True:
        try:
            next_msg = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        # Check if this message belongs to the same stream
        next_event = next_msg.event
        next_stream_id = (
            next_event.stream_id
            if isinstance(next_event, StreamDeltaEvent | StreamEndEvent)
            else None
        )
        same_target = (
            next_msg.channel,
            next_msg.chat_id,
            next_stream_id,
        ) == target_key
        is_delta = isinstance(next_event, StreamDeltaEvent)
        is_end = isinstance(next_event, StreamEndEvent)

        same_metadata = next_msg.metadata == first_msg.metadata
        if same_target and same_metadata and (is_delta or (is_end and next_msg.content)):
            # Accumulate content
            content.append(next_msg.content)
            # If we see stream_end, remember it and stop coalescing this stream
            if isinstance(next_event, StreamEndEvent):
                final_event = StreamEndEvent(
                    stream_id=next_stream_id,
                    resuming=next_event.resuming,
                    merge_next=next_event.merge_next,
                )
                # Stream ended - stop coalescing this stream
                break
        else:
            # First non-matching message defines the coalescing boundary.
            non_matching.append(next_msg)
            break

    merged = replace_outbound_event(first_msg, final_event, content="".join(content))
    return merged, non_matching
