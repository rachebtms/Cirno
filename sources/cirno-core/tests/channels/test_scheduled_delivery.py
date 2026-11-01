"""Exercise scheduled delivery through the real gateway pipeline, without external sends."""

import asyncio
import json
import os
import sqlite3
import subprocess
from functools import partial
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno.agent.loop import AgentLoop
from cirno.agent.tools.context import RequestContext, request_context
from cirno.agent.tools.cron import CronTool
from cirno.agent.tools.message import MessageTool
from cirno.bus.delivery import (
    DELIVERY_RUN_META,
    ChannelNotReadyError,
    DeliveryRejectedError,
    DeliveryRequest,
)
from cirno.bus.events import OutboundMessage
from cirno.bus.outbound_events import ProgressEvent
from cirno.bus.queue import MessageBus
from cirno.channels import outbox as outbox_module
from cirno.channels.base import BaseChannel
from cirno.channels.manager import ChannelManager
from cirno.channels.outbox import DeliveryOutbox
from cirno.channels.registry import load_channel_plugin
from cirno.config.schema import Config
from cirno.cron.bound_runner import run_bound_cron_job
from cirno.cron.service import CronService
from cirno.cron.types import CronSchedule
from cirno.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
from cirno.runtime.admission import RuntimeBusyError, RuntimeMaintenanceError
from cirno.session.manager import SessionManager


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
        while manager.bus.outbound_size or manager._outbound_tasks:
            await asyncio.sleep(0.01)


async def test_parked_gateway_neither_initializes_nor_records_scheduled_delivery(tmp_path):
    manager = make_manager(tmp_path)
    try:
        with manager.bus.admission.pause_before_start():
            manager._dispatch_task = asyncio.create_task(manager._dispatch_outbound())
            await asyncio.sleep(0)
            assert not manager._outbox.path.exists()
            with pytest.raises(RuntimeMaintenanceError):
                await manager.bus.publish_outbound(message())
            with pytest.raises(RuntimeMaintenanceError):
                await manager._recover_scheduled()
            assert not manager._outbox.path.exists()
            assert manager.bus.outbound_size == 0
        await manager.bus.publish_outbound(message())
        assert manager._outbox.path.exists()
    finally:
        await manager.stop_all()


async def test_scheduled_recovery_remains_busy_while_waiting_for_a_send_slot(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    channel = MagicMock(spec=BaseChannel, send=AsyncMock(), stop=AsyncMock())
    channel.has_pending_delivery = False
    manager.channels["whatsapp"] = channel
    manager._outbox.record(message())
    manager._outbound_slots = asyncio.Semaphore(0)
    queued = asyncio.Event()
    queue = manager._queue_outbound

    async def wait_for_slot(channel, msg):
        queued.set()
        await queue(channel, msg)

    monkeypatch.setattr(manager, "_queue_outbound", wait_for_slot)
    recovery = asyncio.create_task(manager._recover_scheduled())
    try:
        await asyncio.wait_for(queued.wait(), 2)
        assert not manager._outbound_tasks
        with pytest.raises(RuntimeBusyError):
            with manager.bus.admission.pause_if_idle(lambda: False):
                pytest.fail("Durable recovery was admitted during maintenance")
        manager._outbound_slots.release()
        await asyncio.wait_for(recovery, 2)
        await drain(manager)
        channel.send.assert_awaited_once()
        assert rows(manager._outbox)[0]["status"] == "sent"
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
            await manager._send_scheduled(channel, msg)
    else:
        await manager._send_scheduled(channel, msg)
    assert rows(manager._outbox)[0]["status"] == "unknown"
    assert DeliveryOutbox(manager._outbox.path).ready() == []
    channel.send.assert_awaited_once()


async def test_legacy_broadcast_has_independent_targets_and_no_foreign_thread_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(outbox_module, "RETRY_SECONDS", 0)
    manager = make_manager(tmp_path)
    tool = MessageTool(send_callback=manager.bus.publish_outbound, workspace=tmp_path)
    with request_context(RequestContext(
        "websocket", "global", session_key="websocket:global", metadata={
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
    await manager._send_scheduled(healthy, messages[0])
    await manager._send_scheduled(offline, messages[1])
    assert [row["status"] for row in rows(manager._outbox)] == ["sent", "pending"]
    assert [msg.channel for msg in manager._outbox.ready()] == ["telegram"]


async def test_queue_acceptance_survives_restart_but_inflight_is_unknown(tmp_path):
    manager = make_manager(tmp_path)
    pending, inflight = message(), message(content="second")
    inflight.chat_id = "other-destination"
    await manager.bus.publish_outbound(pending)
    await manager.bus.publish_outbound(inflight)
    assert manager._outbox.claim(inflight)
    restarted = DeliveryOutbox(manager._outbox.path)
    assert [msg.delivery_id for msg in restarted.ready()] == [pending.delivery_id]
    assert [row["status"] for row in rows(restarted)] == ["pending", "unknown"]


async def test_queue_bounds_expiry_and_untracked_events(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    monkeypatch.setattr(outbox_module, "MAX_PENDING", 1)
    event = message()
    event.event = ProgressEvent(tool_hint=True)
    await manager.bus.publish_outbound(event)
    await manager.bus.publish_outbound(OutboundMessage("slack", "synthetic", "ordinary reply"))
    assert not manager._outbox.path.exists()
    first = message()
    await manager.bus.publish_outbound(first)
    with pytest.raises(RuntimeError, match="queue is full"):
        await manager.bus.publish_outbound(message(content="second"))
    with pytest.raises(ValueError, match="1 MiB"):
        await manager.bus.publish_outbound(message(content="a" * (1024 * 1024)))
    monkeypatch.setattr(outbox_module, "MAX_AGE_SECONDS", 0)
    assert manager._outbox.ready() == []
    assert rows(manager._outbox)[0]["error"] == "expired"
    assert not manager._outbox.claim(first)
    if os.name != "nt":
        assert manager._outbox.path.stat().st_mode & 0o777 == 0o600


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
        await manager._send_scheduled(channel, msg)
        channel.send.assert_not_called()
        assert rows(manager._outbox)[0]["error"] == "session_replaced"
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
    await manager._send_scheduled(channel, first)
    channel.send.side_effect = None
    await manager._send_scheduled(channel, second)
    await manager._send_scheduled(channel, other)
    assert [call.args[0].content for call in channel.send.await_args_list] == ["first", "other"]
    manager.channels["whatsapp"] = channel
    await manager._recover_scheduled()
    await drain(manager)
    assert [call.args[0].content for call in channel.send.await_args_list] == ["first", "other", "first", "second"]
    # A stale queued copy must not downgrade the durable successful result.
    manager._outbox.finish(first, "failed", "channel_disabled")
    assert all(row["status"] == "sent" for row in rows(manager._outbox))


async def test_relocated_instance_finds_queue_and_disabled_channel_does_not_send(tmp_path):
    original = tmp_path / "original"
    manager = make_manager(original)
    await manager.bus.publish_outbound(message())
    moved = tmp_path / "moved"
    original.rename(moved)
    restarted = make_manager(moved)
    await restarted._recover_scheduled()
    assert rows(restarted._outbox)[0]["error"] == "channel_disabled"
    assert not original.exists()


async def test_recovery_rechecks_attachment_workspace_boundary(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    session = await sessions.state.get("whatsapp:synthetic")
    manager = make_manager(tmp_path, sessions)
    manager.config.agents.defaults.workspace = str(workspace)
    manager.config.tools.restrict_to_workspace = True
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
        await manager._send_scheduled(channel, msg)
        channel.send.assert_not_called()
        assert rows(manager._outbox)[0]["error"] == "attachment_access_denied"
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("name", ["telegram"])
async def test_unavailable_adapter_does_not_report_success(name, monkeypatch):
    cls = load_channel_plugin(name).load_channel_class()
    channel = cls(cls.default_config(), MessageBus())
    with pytest.raises((ChannelNotReadyError, DeliveryRejectedError)):
        await channel.send(OutboundMessage(name, "synthetic", "result"))
