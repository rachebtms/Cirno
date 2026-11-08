"""Exercise scheduled delivery through the real gateway pipeline, without external sends."""

import asyncio
import os
import sqlite3
import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.message import MessageTool
from cirno_core.bus.delivery import (
    DELIVERY_RUN_META,
    ChannelNotReadyError,
    DeliveryRejectedError,
    DeliveryRequest,
)
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.runtime.admission import RuntimeBusyError, RuntimeMaintenanceError
from cirno_core.session.manager import SessionManager
from cirno_server.channels import outbox as outbox_module
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.manager import ChannelManager
from cirno_server.channels.outbox import DeliveryOutbox
from cirno_server.channels.registry import load_channel_plugin


def rows(outbox):
    with sqlite3.connect(outbox.path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM deliveries ORDER BY created")]


def make_manager(tmp_path, sessions=None):
    config = Config.model_validate({"channels": {
        "websocket": {"enabled": False}, "sendProgress": False, "sendToolHints": False,
    }})
    bus = MessageBus()
    manager = ChannelManager(config, bus, config_path=tmp_path / "config.json", session_manager=sessions)
    return manager


def message(channel="whatsapp", content="result", generation=None):
    return OutboundMessage(channel, "synthetic", content,
                           delivery=DeliveryRequest("run-1", "whatsapp:synthetic", generation))


async def drain(manager):
    async with asyncio.timeout(5):
        while manager.bus.outbound_size or manager.delivery.tasks:
            await asyncio.sleep(0.01)


async def test_parked_gateway_neither_initializes_nor_records_scheduled_delivery(tmp_path):
    manager = make_manager(tmp_path)
    try:
        with manager.bus.admission.pause_before_start():
            manager._dispatch_task = asyncio.create_task(manager.dispatcher.run())
            await asyncio.sleep(0)
            assert not manager.delivery.durable.outbox.path.exists()
            with pytest.raises(RuntimeMaintenanceError):
                await manager.bus.publish_outbound(message())
            with pytest.raises(RuntimeMaintenanceError):
                await manager.dispatcher.recover()
            assert not manager.delivery.durable.outbox.path.exists()
            assert manager.bus.outbound_size == 0
        await manager.bus.publish_outbound(message())
        assert manager.delivery.durable.outbox.path.exists()
    finally:
        await manager.stop_all()


async def test_scheduled_recovery_remains_busy_while_waiting_for_a_send_slot(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    channel = MagicMock(spec=BaseChannel, send=AsyncMock(), stop=AsyncMock())
    channel.has_pending_delivery = False
    manager.runtimes.channels["whatsapp"] = channel
    manager.delivery.durable.outbox.record(message())
    manager.delivery.pending_slots = asyncio.Semaphore(0)
    queued = asyncio.Event()
    queue = manager.delivery.queue

    async def wait_for_slot(channel, msg):
        queued.set()
        await queue(channel, msg)

    monkeypatch.setattr(manager.delivery, "queue", wait_for_slot)
    recovery = asyncio.create_task(manager.dispatcher.recover())
    try:
        await asyncio.wait_for(queued.wait(), 2)
        assert not manager.delivery.tasks
        with pytest.raises(RuntimeBusyError):
            with manager.bus.admission.pause_if_idle(lambda: False):
                pytest.fail("Durable recovery was admitted during maintenance")
        manager.delivery.pending_slots.release()
        await asyncio.wait_for(recovery, 2)
        await drain(manager)
        channel.send.assert_awaited_once()
        assert rows(manager.delivery.durable.outbox)[0]["status"] == "sent"
    finally:
        recovery.cancel()
        await asyncio.gather(recovery, return_exceptions=True)
        await manager.stop_all()




@pytest.mark.parametrize("failure", [TimeoutError("response lost"), asyncio.CancelledError()])
async def test_uncertain_attempt_is_not_replayed(tmp_path, failure):
    manager = make_manager(tmp_path)
    channel = MagicMock(spec=BaseChannel)
    channel.send = AsyncMock(side_effect=failure)
    msg = message()
    await manager.bus.publish_outbound(msg)
    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await manager.delivery.durable.send(channel, msg)
    else:
        await manager.delivery.durable.send(channel, msg)
    assert rows(manager.delivery.durable.outbox)[0]["status"] == "unknown"
    assert DeliveryOutbox(manager.delivery.durable.outbox.path).ready() == []
    channel.send.assert_awaited_once()


async def test_legacy_broadcast_has_independent_targets_and_no_foreign_thread_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(outbox_module, "RETRY_SECONDS", 0)
    manager = make_manager(tmp_path)
    tool = MessageTool(send_callback=manager.bus.publish_outbound, workspace=tmp_path)
    with request_context(RequestContext(
        "websocket", "cirno", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", metadata={
            DELIVERY_RUN_META: "run-1", "message_thread_id": 42, "message_id": "parent",
        },
    )):
        for chat_id in ("one", "two"):
            assert str(await tool.execute(content="result", channel="telegram", chat_id=chat_id)).startswith("Message queued")
    messages = [manager.bus.outbound.get_nowait() for _ in range(2)]
    assert all("message_thread_id" not in msg.metadata and "message_id" not in msg.metadata for msg in messages)
    assert len({msg.delivery_id for msg in messages}) == 2
    healthy = MagicMock(spec=BaseChannel, send=AsyncMock())
    offline = MagicMock(spec=BaseChannel, send=AsyncMock(side_effect=ChannelNotReadyError()))
    await manager.delivery.durable.send(healthy, messages[0])
    await manager.delivery.durable.send(offline, messages[1])
    assert [row["status"] for row in rows(manager.delivery.durable.outbox)] == ["sent", "pending"]
    assert [msg.channel for msg in manager.delivery.durable.outbox.ready()] == ["telegram"]


async def test_queue_acceptance_survives_restart_but_inflight_is_unknown(tmp_path):
    manager = make_manager(tmp_path)
    pending, inflight = message(), message(content="second")
    inflight.chat_id = "other-destination"
    await manager.bus.publish_outbound(pending)
    await manager.bus.publish_outbound(inflight)
    assert manager.delivery.durable.outbox.claim(inflight)
    restarted = DeliveryOutbox(manager.delivery.durable.outbox.path)
    assert [msg.delivery_id for msg in restarted.ready()] == [pending.delivery_id]
    assert [row["status"] for row in rows(restarted)] == ["pending", "unknown"]


async def test_queue_bounds_expiry_and_untracked_events(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(outbox_module, "MAX_PENDING", 1)
    event = message()
    event.event = ProgressEvent(tool_hint=True)
    await manager.bus.publish_outbound(event)
    await manager.bus.publish_outbound(OutboundMessage("slack", "synthetic", "ordinary reply"))
    assert not manager.delivery.durable.outbox.path.exists()
    first = message()
    await manager.bus.publish_outbound(first)
    with pytest.raises(RuntimeError, match="queue is full"):
        await manager.bus.publish_outbound(message(content="second"))
    with pytest.raises(ValueError, match="1 MiB"):
        await manager.bus.publish_outbound(message(content="a" * (1024 * 1024)))
    monkeypatch.setattr(outbox_module, "MAX_AGE_SECONDS", 0)
    assert manager.delivery.durable.outbox.ready() == []
    assert rows(manager.delivery.durable.outbox)[0]["error"] == "expired"
    assert not manager.delivery.durable.outbox.claim(first)
    if os.name != "nt":
        assert manager.delivery.durable.outbox.path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("operation", ["delete", "reset"])
async def test_pending_result_cannot_send_after_source_session_is_replaced(tmp_path, operation):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    session = await sessions.state.get("whatsapp:synthetic")
    manager = make_manager(tmp_path, sessions)
    channel = MagicMock(spec=BaseChannel, send=AsyncMock())
    msg = message(generation=session.generation)
    try:
        await manager.bus.publish_outbound(msg)
        await getattr(sessions.state, operation)(session.key)
        await manager.delivery.durable.send(channel, msg)
        channel.send.assert_not_called()
        assert rows(manager.delivery.durable.outbox)[0]["error"] == "session_replaced"
    finally:
        await sessions.state.aclose()


async def test_recovery_keeps_destination_order_and_does_not_block_other_chats(tmp_path, monkeypatch):
    monkeypatch.setattr(outbox_module, "RETRY_SECONDS", 0)
    manager = make_manager(tmp_path)
    first, second, other = message(content="first"), message(content="second"), message(content="other")
    other.chat_id = "another-chat"
    for msg in (first, second, other):
        await manager.bus.publish_outbound(msg)
        await manager.bus.consume_outbound()
    channel = MagicMock(spec=BaseChannel, send=AsyncMock(side_effect=ChannelNotReadyError()))
    await manager.delivery.durable.send(channel, first)
    channel.send.side_effect = None
    await manager.delivery.durable.send(channel, second)
    await manager.delivery.durable.send(channel, other)
    assert [call.args[0].content for call in channel.send.await_args_list] == ["first", "other"]
    manager.runtimes.channels["whatsapp"] = channel
    await manager.dispatcher.recover()
    await drain(manager)
    assert [call.args[0].content for call in channel.send.await_args_list] == ["first", "other", "first", "second"]
    # A stale queued copy must not downgrade the durable successful result.
    manager.delivery.durable.outbox.finish(first, "failed", "channel_disabled")
    assert all(row["status"] == "sent" for row in rows(manager.delivery.durable.outbox))


async def test_relocated_instance_finds_queue_and_disabled_channel_does_not_send(tmp_path):
    original = tmp_path / "original"
    manager = make_manager(original)
    await manager.bus.publish_outbound(message())
    moved = tmp_path / "moved"
    original.rename(moved)
    restarted = make_manager(moved)
    await restarted.dispatcher.recover()
    assert rows(restarted.delivery.durable.outbox)[0]["error"] == "channel_disabled"
    assert not original.exists()


async def test_recovery_rechecks_attachment_workspace_boundary(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    session = await sessions.state.get("whatsapp:synthetic")
    manager = make_manager(tmp_path, sessions)
    manager.runtimes.config.agents.defaults.workspace = str(workspace)
    manager.runtimes.config.tools.restrict_to_workspace = True
    reports = workspace / "reports"
    reports.mkdir()
    attachment = reports / "report.txt"
    attachment.write_text("report")
    msg = message(generation=session.generation)
    msg.media = [str(attachment)]
    channel = MagicMock(spec=BaseChannel, send=AsyncMock())
    try:
        await manager.bus.publish_outbound(msg)
        attachment.unlink()
        reports.rmdir()
        private = tmp_path / "private"
        private.mkdir()
        (private / "report.txt").write_text("not authorized")
        if os.name == "nt":
            # Directory junctions resolve across the same workspace boundary
            # without requiring Windows' privileged symlink capability.
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(reports), str(private)],
                check=True, capture_output=True,
            )
        else:
            reports.symlink_to(private, target_is_directory=True)
        await manager.delivery.durable.send(channel, msg)
        channel.send.assert_not_called()
        assert rows(manager.delivery.durable.outbox)[0]["error"] == "attachment_access_denied"
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("name", ["telegram"])
async def test_unavailable_adapter_does_not_report_success(name, monkeypatch):
    cls = load_channel_plugin(name).load_channel_class()
    channel = cls(cls.default_config(), MessageBus())
    with pytest.raises((ChannelNotReadyError, DeliveryRejectedError)):
        await channel.send(OutboundMessage(name, "synthetic", "result"))


async def test_delivery_generation_check_does_not_load_the_model_checkpoint(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    session = await sessions.state.get("whatsapp:synthetic")
    # Loading the full snapshot can materialize a long-running model request.
    # Generation and attachment policy need only the lightweight header.
    monkeypatch.setattr(sessions.state, "read", AsyncMock(side_effect=AssertionError("full model snapshot loaded")))
    manager = make_manager(tmp_path, sessions)
    channel = MagicMock(spec=BaseChannel, send=AsyncMock())
    msg = message(generation=session.generation)
    try:
        await manager.bus.publish_outbound(msg)
        await manager.delivery.durable.send(channel, msg)
        channel.send.assert_awaited_once()
        assert rows(manager.delivery.durable.outbox)[0]["status"] == "sent"
    finally:
        await sessions.state.aclose()


async def test_unknown_delivery_keeps_receipt_and_logs_transport_exception(tmp_path):
    from loguru import logger

    manager = make_manager(tmp_path)
    channel = MagicMock(spec=BaseChannel, send=AsyncMock(side_effect=TimeoutError("response lost")))
    msg = message()
    await manager.bus.publish_outbound(msg)
    records = []
    sink = logger.add(lambda entry: records.append(entry.record), level="ERROR")
    try:
        await manager.delivery.durable.send(channel, msg)
        assert rows(manager.delivery.durable.outbox)[0]["status"] == "unknown"
        assert manager.delivery.durable.outbox.ready() == []
        assert any(record["exception"] and record["exception"].type is TimeoutError for record in records)
    finally:
        logger.remove(sink)
        await manager.stop_all()
