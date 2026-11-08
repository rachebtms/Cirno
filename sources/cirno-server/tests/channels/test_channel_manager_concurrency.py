import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeBusyError
from cirno_server.channels.delivery import queue as queue_module
from cirno_server.channels.delivery import retry as retry_module
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.manager import ChannelManager


def make_manager():
    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    manager = ChannelManager(config, MessageBus())
    channel = MagicMock(spec=BaseChannel)
    channel.send = AsyncMock()
    channel.stop = AsyncMock()
    channel.has_pending_delivery = False
    manager.runtimes.channels["websocket"] = channel
    return manager, channel


async def test_delivery_has_no_idle_gap_between_queue_dispatch_and_send(monkeypatch):
    manager, channel = make_manager()
    started, release = asyncio.Event(), asyncio.Event()
    observations = []
    consume = manager.bus.consume_outbound

    def require_busy():
        if manager.bus.admission.paused:
            observations.append("parked")
            return
        with pytest.raises(RuntimeBusyError):
            with manager.bus.admission.pause_if_idle(lambda: False):
                pytest.fail("Delivery was incorrectly reported idle")
        observations.append("busy")
        assert not manager.bus.admission.paused

    async def dequeue():
        message = await consume()
        asyncio.get_running_loop().call_soon(require_busy)
        return message

    async def send(message):
        started.set()
        await release.wait()

    monkeypatch.setattr(manager.bus, "consume_outbound", dequeue)
    channel.send.side_effect = send
    await manager.bus.publish_outbound(OutboundMessage("websocket", "chat", "final reply"))
    require_busy()
    manager._dispatch_task = asyncio.create_task(manager.dispatcher.run())
    try:
        await asyncio.wait_for(started.wait(), 2)
        assert manager.bus.outbound_size == 0
        require_busy()
        assert observations == ["busy", "busy", "busy"]
        release.set()
        await wait_until(lambda: not manager.has_pending_delivery)
        with manager.bus.admission.pause_if_idle(lambda: False):
            assert manager.bus.admission.paused
            # A late producer may queue a lifecycle notice while the consumer
            # is awaiting an empty queue. It must remain parked until admission
            # is restored, rather than start new transport writes under the gate.
            await manager.bus.publish_outbound(OutboundMessage("websocket", "chat", "late notice"))
            await wait_until(lambda: manager.dispatcher.dispatching)
            await wait_until(lambda: len(observations) == 4)
            channel.send.assert_awaited_once()
        assert not manager.bus.admission.paused
        await wait_until(lambda: not manager.has_pending_delivery)
        assert [call.args[0].content for call in channel.send.await_args_list] == ["final reply", "late notice"]
        assert observations == ["busy", "busy", "busy", "parked"]
    finally:
        release.set()
        await manager.stop_all()


async def wait_until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


async def test_ten_chats_keep_order_while_one_destination_is_blocked():
    manager, channel = make_manager()
    release = asyncio.Event()
    started = asyncio.Event()
    received = {str(i): [] for i in range(10)}

    async def send(msg):
        if msg.chat_id == "0":
            started.set()
            await release.wait()
        received[msg.chat_id].append(msg.content)

    channel.send.side_effect = send
    manager._dispatch_task = asyncio.create_task(manager.dispatcher.run())
    try:
        for content in ("first", "last"):
            for i in range(10):
                await manager.bus.publish_outbound(OutboundMessage("websocket", str(i), content))
        await asyncio.wait_for(started.wait(), 2)
        await wait_until(lambda: all(len(received[str(i)]) == 2 for i in range(1, 10)))
        assert received["0"] == []
        assert all(received[str(i)] == ["first", "last"] for i in range(1, 10))
        release.set()
        await wait_until(lambda: not manager.delivery.tasks)
        assert received["0"] == ["first", "last"]
        assert manager.delivery.tails == {}
    finally:
        await manager.stop_all()


async def test_retry_does_not_block_other_chats(monkeypatch):
    monkeypatch.setattr(retry_module, "RETRY_DELAYS", (0.1,))
    manager, channel = make_manager()
    retry_started = asyncio.Event()
    healthy_sent = asyncio.Event()
    attempts = 0

    async def send(msg):
        nonlocal attempts
        if msg.chat_id == "retry":
            attempts += 1
            if attempts == 1:
                retry_started.set()
                raise OSError("temporary failure")
            assert healthy_sent.is_set()
        else:
            healthy_sent.set()

    channel.send.side_effect = send
    channel.should_retry_send_error.return_value = True
    try:
        await manager.delivery.queue(channel, OutboundMessage("websocket", "retry", "a"))
        await asyncio.wait_for(retry_started.wait(), 2)
        await manager.delivery.queue(channel, OutboundMessage("websocket", "healthy", "b"))
        await wait_until(lambda: not manager.delivery.tasks)
        assert attempts == 2
        assert healthy_sent.is_set()
    finally:
        await manager.delivery.cancel()


async def test_pending_and_concurrent_sends_are_bounded_and_cancellable(monkeypatch):
    monkeypatch.setattr(queue_module, "PENDING_LIMIT", 4)
    monkeypatch.setattr(queue_module, "SEND_CONCURRENCY", 2)
    manager, channel = make_manager()
    blocked = asyncio.Event()
    active = 0
    peak = 0

    async def send(msg):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await blocked.wait()
        finally:
            active -= 1

    channel.send.side_effect = send
    for i in range(4):
        await manager.delivery.queue(channel, OutboundMessage("websocket", str(i), "a"))
    extra = asyncio.create_task(manager.delivery.queue(
        channel, OutboundMessage("websocket", "extra", "a"),
    ))
    try:
        await wait_until(lambda: active == 2)
        assert not extra.done()
        assert len(manager.delivery.tasks) == 4
        extra.cancel()
        await asyncio.gather(extra, return_exceptions=True)
        await manager.delivery.cancel()
        assert peak == 2
        assert active == 0
        assert not manager.delivery.tasks
        assert not manager.delivery.tails
        # Cancellation returns admission permits, including tasks not yet sending.
        for i in range(4):
            await asyncio.wait_for(manager.delivery.queue(
                channel, OutboundMessage("websocket", str(i), "b"),
            ), 2)
    finally:
        extra.cancel()
        await asyncio.gather(extra, return_exceptions=True)
        await manager.delivery.cancel()


async def test_channel_stop_cancels_only_its_sends_before_stopping_runtime():
    manager, channel = make_manager()
    active = asyncio.Event()
    cancelled = asyncio.Event()

    async def send(msg):
        active.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def stop():
        assert cancelled.is_set()

    channel.send.side_effect = send
    channel.stop.side_effect = stop
    other = MagicMock(spec=BaseChannel)
    other.send = AsyncMock()
    manager.runtimes.channels["other"] = other
    await manager.delivery.queue(channel, OutboundMessage("websocket", "a", "1"))
    await asyncio.wait_for(active.wait(), 2)
    await manager.runtimes.stop("websocket")
    await manager.delivery.queue(other, OutboundMessage("other", "b", "2"))
    await wait_until(lambda: not manager.delivery.tasks)
    other.send.assert_awaited_once()
    assert not manager.delivery.tails


async def test_dispatcher_shutdown_cleans_active_and_waiting_destination_tasks():
    manager, channel = make_manager()
    active = asyncio.Event()
    cancelled = asyncio.Event()

    async def send(msg):
        active.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    channel.send.side_effect = send
    manager._dispatch_task = asyncio.create_task(manager.dispatcher.run())
    try:
        for content in ("one", "two", "three"):
            await manager.bus.publish_outbound(OutboundMessage("websocket", "chat", content))
        await asyncio.wait_for(active.wait(), 2)
        await wait_until(lambda: len(manager.delivery.tasks) == 3)
    finally:
        await manager.stop_all()
    assert cancelled.is_set()
    channel.send.assert_awaited_once()
    assert not manager.delivery.tasks
    assert not manager.delivery.tails


async def test_all_send_slots_in_backoff_leave_healthy_chat_and_fifo_live(monkeypatch):
    monkeypatch.setattr(retry_module, "RETRY_DELAYS", (0.6,))
    manager, channel = make_manager()
    failed = set()
    delivered = []

    async def send(msg):
        if msg.chat_id != "healthy" and msg.chat_id not in failed:
            failed.add(msg.chat_id)
            raise OSError("temporary failure")
        delivered.append((msg.chat_id, msg.content))

    channel.send.side_effect = send
    channel.should_retry_send_error.return_value = True
    try:
        for i in range(queue_module.SEND_CONCURRENCY):
            await manager.delivery.queue(channel, OutboundMessage("websocket", str(i), "first"))
        await wait_until(lambda: len(failed) == queue_module.SEND_CONCURRENCY)
        await manager.delivery.queue(channel, OutboundMessage("websocket", "0", "last"))
        await manager.delivery.queue(channel, OutboundMessage("websocket", "healthy", "ok"))
        async with asyncio.timeout(0.2):
            while ("healthy", "ok") not in delivered:
                await asyncio.sleep(0)
        assert ("0", "last") not in delivered
        await wait_until(lambda: not manager.delivery.tasks)
        assert [content for chat, content in delivered if chat == "0"] == ["first", "last"]
    finally:
        await manager.delivery.cancel()
    assert not manager.delivery.tails


async def test_scheduled_cancel_waiting_for_permit_does_not_claim(tmp_path, monkeypatch):
    from cirno_core.bus.delivery import DeliveryRequest

    monkeypatch.setattr(queue_module, "SEND_CONCURRENCY", 1)
    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    manager = ChannelManager(config, MessageBus(), config_path=tmp_path / "config.json")
    channel = MagicMock(spec=BaseChannel, send=AsyncMock())
    manager.runtimes.channels["websocket"] = channel
    msg = OutboundMessage("websocket", "scheduled", "result",
                          delivery=DeliveryRequest("run", "websocket:scheduled", None))
    manager.delivery.durable.outbox.record(msg)
    claim = MagicMock(wraps=manager.delivery.durable.outbox.claim)
    monkeypatch.setattr(manager.delivery.durable.outbox, "claim", claim)
    await manager.delivery.send_slots.acquire()
    try:
        await manager.delivery.queue(channel, msg)
        await asyncio.sleep(0)
        await manager.delivery.cancel()
        claim.assert_not_called()
        channel.send.assert_not_awaited()
        assert [item.delivery_id for item in manager.delivery.durable.outbox.ready()] == [msg.delivery_id]
        assert not manager.delivery.scheduled
    finally:
        manager.delivery.send_slots.release()
        await manager.delivery.cancel()


async def test_restart_notice_does_not_outwait_send_permit_deadline(tmp_path):
    from cirno_core.utils.restart import RestartNotice

    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    manager = ChannelManager(config, MessageBus(), config_path=tmp_path / "config.json")
    channel = MagicMock(spec=BaseChannel, is_running=True)
    active = 0
    release = asyncio.Event()
    notices = []

    async def send(msg):
        nonlocal active
        if msg.chat_id == "notice":
            notices.append(msg)
            return
        active += 1
        try:
            await release.wait()
        finally:
            active -= 1

    channel.send = AsyncMock(side_effect=send)
    manager.runtimes.channels["probe"] = channel
    try:
        for i in range(queue_module.SEND_CONCURRENCY):
            await manager.delivery.queue(channel, OutboundMessage("probe", str(i), "blocked"))
        await wait_until(lambda: active == queue_module.SEND_CONCURRENCY)
        await asyncio.wait_for(manager._send_restart_notice_when_started(
            RestartNotice(channel="probe", chat_id="notice", started_at_raw=""), timeout_s=0.05,
        ), 1)
        assert notices == []
        assert active == queue_module.SEND_CONCURRENCY
    finally:
        await manager.delivery.cancel()
    assert active == 0
    assert manager.delivery.send_slots._value == queue_module.SEND_CONCURRENCY


async def test_restart_notice_deadline_does_not_cancel_submitted_send(tmp_path):
    from cirno_core.utils.restart import RestartNotice

    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    manager = ChannelManager(config, MessageBus(), config_path=tmp_path / "config.json")
    started = asyncio.Event()
    release = asyncio.Event()

    async def send(msg):
        started.set()
        await release.wait()

    channel = MagicMock(spec=BaseChannel, is_running=True, send=AsyncMock(side_effect=send))
    manager.runtimes.channels["probe"] = channel
    task = asyncio.create_task(manager._send_restart_notice_when_started(
        RestartNotice(channel="probe", chat_id="notice", started_at_raw=""), timeout_s=0.05,
    ))
    try:
        await asyncio.wait_for(started.wait(), 1)
        try:
            await asyncio.wait_for(asyncio.shield(task), 0.1)
        except TimeoutError:
            pass
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, 1)
        channel.send.assert_awaited_once()
        assert manager.delivery.send_slots._value == queue_module.SEND_CONCURRENCY
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
