"""Retry budgets, streaming contracts and cancellation without optional adapters."""

import asyncio
from unittest.mock import AsyncMock, Mock, call

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import (
    StreamDeltaEvent,
    StreamedResponseEvent,
    StreamEndEvent,
    outbound_message_for_event,
)
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery import retry as retry_module
from cirno_server.channels.delivery.retry import RetrySender


@pytest.mark.parametrize(("limit", "fails", "attempts", "waits"), [
    (3, False, 1, 0), (3, True, 3, 2), (0, True, 1, 0),
])
async def test_retry_budget_includes_initial_attempt(monkeypatch, limit, fails, attempts, waits):
    channel = Mock(spec=BaseChannel, send=AsyncMock(), should_retry_send_error=Mock(return_value=True))
    if fails:
        channel.send.side_effect = OSError("offline")
    sleep = AsyncMock()
    monkeypatch.setattr(retry_module.asyncio, "sleep", sleep)
    sender = RetrySender(asyncio.Semaphore(32), lambda: limit)
    await sender.send(channel, OutboundMessage("test", "123", "result"))
    assert channel.send.await_count == attempts
    assert sleep.await_count == waits
    assert sender.slots._value == 32


async def test_stream_delivery_preserves_response_boundaries():
    channel = Mock(spec=BaseChannel, send=AsyncMock(), send_delta=AsyncMock())
    sender = RetrySender(asyncio.Semaphore(32), lambda: 3)
    for event in (StreamDeltaEvent(content="delta", stream_id="s1"),
                  StreamEndEvent(content="", stream_id="s1", resuming=True, merge_next=True)):
        message = outbound_message_for_event(channel="test", chat_id="123", event=event)
        await sender.send(channel, message)
    assert channel.send_delta.await_args_list == [
        call("123", "delta", {}, stream_id="s1", stream_end=False, resuming=False, merge_next=False),
        call("123", "", {}, stream_id="s1", stream_end=True, resuming=True, merge_next=True),
    ]
    channel.send.assert_not_awaited()


async def test_stream_completion_marker_does_not_send_text_again():
    channel = Mock(spec=BaseChannel, send=AsyncMock(), send_delta=AsyncMock())
    sender = RetrySender(asyncio.Semaphore(32), lambda: 3)
    message = outbound_message_for_event(channel="test", chat_id="123", event=StreamedResponseEvent(), content="result")
    await sender.send(channel, message)
    channel.send.assert_not_awaited()
    channel.send_delta.assert_not_awaited()


@pytest.mark.parametrize("during_backoff", [False, True])
async def test_cancellation_propagates_and_releases_send_permit(monkeypatch, during_backoff):
    channel = Mock(spec=BaseChannel, send=AsyncMock(), should_retry_send_error=Mock(return_value=True))
    channel.send.side_effect = OSError("offline") if during_backoff else asyncio.CancelledError()
    sleep = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(retry_module.asyncio, "sleep", sleep)
    sender = RetrySender(asyncio.Semaphore(32), lambda: 3)
    with pytest.raises(asyncio.CancelledError):
        await sender.send(channel, OutboundMessage("test", "123", "result"))
    channel.send.assert_awaited_once()
    assert sleep.await_count == int(during_backoff)
    assert sender.slots._value == 32
