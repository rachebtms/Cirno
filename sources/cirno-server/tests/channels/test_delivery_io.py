"""Durable outbox I/O keeps the gateway live without losing cancellation receipts."""

import asyncio
import sqlite3
from threading import Event
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.bus.delivery import DeliveryRequest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeBusyError
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.durable import DurableDelivery


def setup(tmp_path):
    bus = MessageBus()
    delivery = DurableDelivery(bus, tmp_path / "config.json", None, Config)
    message = OutboundMessage("test", "chat", "Result", delivery=DeliveryRequest("run", "test:chat", None))
    channel = MagicMock(spec=BaseChannel, send=AsyncMock())
    return bus, delivery, message, channel


def status(delivery):
    with sqlite3.connect(delivery.outbox.path) as db:
        return db.execute("SELECT status FROM deliveries").fetchone()[0]


@pytest.mark.parametrize("operation", ["record", "ready", "claim", "finish"])
async def test_outbox_operations_do_not_block_other_gateway_work(tmp_path, monkeypatch, operation):
    bus, delivery, message, channel = setup(tmp_path)
    if operation != "record":
        await bus.publish_outbound(message)
    loop = asyncio.get_running_loop()
    original = getattr(delivery.outbox, operation)

    def stalled(*args, **kwargs):
        responsive = Event()
        loop.call_soon_threadsafe(responsive.set)
        assert responsive.wait(1), "Outbox storage blocked the gateway event loop"
        return original(*args, **kwargs)

    monkeypatch.setattr(delivery.outbox, operation, stalled)
    if operation == "record":
        await bus.publish_outbound(message)
        assert status(delivery) == "pending"
    elif operation == "ready":
        assert len(await delivery.ready()) == 1
    else:
        await delivery.send(channel, message)
        channel.send.assert_awaited_once()
        assert status(delivery) == "sent"


@pytest.mark.parametrize("operation", ["record", "claim", "finish"])
async def test_cancel_waits_for_storage_and_retains_the_correct_delivery_state(tmp_path, monkeypatch, operation):
    bus, delivery, message, channel = setup(tmp_path)
    if operation != "record":
        await bus.publish_outbound(message)
    entered, release = Event(), Event()
    original = getattr(delivery.outbox, operation)

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(delivery.outbox, operation, delayed)
    task = asyncio.create_task(bus.publish_outbound(message) if operation == "record" else delivery.send(channel, message))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        if operation == "record":
            with pytest.raises(RuntimeBusyError):
                with bus.admission.pause_if_idle(lambda: False):
                    pytest.fail("An admitted delivery was still being persisted")
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert status(delivery) == ("sent" if operation == "finish" else "pending")
    if operation == "record":
        assert bus.outbound_size == 1
        assert (await bus.consume_outbound()).delivery_id == message.delivery_id
    if operation != "finish":
        channel.send.assert_not_awaited()
