"""Task inbox acknowledgements remain truthful through failed or cancelled saves."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.subagents.contracts import SubagentControlError, SubagentOutcome
from cirno_core.agent.subagents.manager import SubagentManager
from cirno_core.agent.subagents.status import SubagentSessionError
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.subagent import SubagentTool
from cirno_core.bus.queue import MessageBus
from cirno_core.session.manager import SessionManager


@pytest.fixture
async def live_task(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    parent = await sessions.state.get_header("websocket:inbox")
    bus = MessageBus()
    manager = SubagentManager(tmp_path / "workspace", bus, 1000, consolidator=Mock(), session_manager=sessions)
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(_record):
        entered.set()
        await release.wait()
        return SubagentOutcome("done", "Local fixture result")

    manager.execution.run = execute
    record = await manager._create_task(
        "Inspect local fixture", None, "websocket", "inbox", parent.key, None, None,
        None, SimpleNamespace(), announce=True, origin_turn_id=None, session_policy=None,
    )
    execution = manager._running_tasks[record.status.task_id]
    await entered.wait()
    try:
        yield sessions, parent, manager, record, release, execution
    finally:
        release.set()
        await asyncio.gather(execution, return_exceptions=True)
        await asyncio.sleep(0)
        await manager.close()
        await sessions.state.aclose()


async def test_accepted_message_reports_receipt_save_failure_without_inviting_duplicate_send(live_task, monkeypatch):
    _sessions, parent, manager, record, _finish, _execution = live_task
    monkeypatch.setattr(manager.sessions, "save", AsyncMock(side_effect=OSError("Fixture save failure")))
    with request_context(RequestContext("websocket", "inbox", session_key=parent.key)):
        response = await SubagentTool(manager).execute("send", record.status.task_id, message="Inspect once")
    assert not is_tool_error_result(response)
    receipt = json.loads(response)
    assert receipt["receipt"] == "accepted"
    assert receipt["persisted"] is False
    assert "resend" in receipt["warning"].lower()
    assert record.inbox == [(receipt["message_id"], "Inspect once")]
    assert manager.check(record.status.task_id, parent.key).receipts[receipt["message_id"]] == "accepted"


@pytest.mark.parametrize("cancel", [False, True])
async def test_failed_or_cancelled_drain_does_not_claim_delivery_or_drop_body(live_task, monkeypatch, cancel):
    _sessions, parent, manager, record, finish, execution = live_task
    receipt = await manager.send(record.status.task_id, parent.key, "Retain this body")
    save_entered, save_release = asyncio.Event(), asyncio.Event()
    save = manager.sessions.save

    async def gated_save(status):
        save_entered.set()
        await save_release.wait()
        if not cancel:
            raise OSError("Fixture receipt write failure")
        return await save(status)

    monkeypatch.setattr(manager.sessions, "save", gated_save)
    pending = asyncio.create_task(manager._drain_inbox(record))
    try:
        await save_entered.wait()
        if cancel:
            pending.cancel()
        save_release.set()
        with pytest.raises(asyncio.CancelledError if cancel else OSError):
            await pending
        assert record.inbox == [(receipt["message_id"], "Retain this body")]
        assert record.status.receipts[receipt["message_id"]] == "accepted"
        finish.set()
        await execution
        assert record.status.receipts[receipt["message_id"]] == "undelivered"
    finally:
        save_release.set()


async def test_ending_task_during_receipt_save_is_not_misreported_as_save_failure(live_task, monkeypatch):
    sessions, parent, manager, record, finish, execution = live_task
    entered, release = asyncio.Event(), asyncio.Event()
    save = manager.sessions.save
    gated = False

    async def delayed_save(status):
        nonlocal gated
        if status.receipts and not gated:
            gated = True
            entered.set()
            await release.wait()
        return await save(status)

    monkeypatch.setattr(manager.sessions, "save", delayed_save)
    sending = asyncio.create_task(manager.send(record.status.task_id, parent.key, "Queued once"))
    try:
        await entered.wait()
        finish.set()
        await execution
        await asyncio.sleep(0)
    finally:
        release.set()
    receipt = await sending
    assert "warning" not in receipt
    assert "persisted" not in receipt
    header = await sessions.state.read_header(record.session.key)
    assert header.metadata["subagent_task"]["receipts"][receipt["message_id"]] == "undelivered"


async def test_drain_keeps_messages_accepted_during_its_save_in_the_next_snapshot(live_task, monkeypatch):
    _sessions, parent, manager, record, _finish, _execution = live_task
    first = await manager.send(record.status.task_id, parent.key, "First")
    entered, release = asyncio.Event(), asyncio.Event()
    save = manager.sessions.save
    gated = False

    async def delayed_save(status):
        nonlocal gated
        if not gated:
            gated = True
            entered.set()
            await release.wait()
        return await save(status)

    monkeypatch.setattr(manager.sessions, "save", delayed_save)
    draining = asyncio.create_task(manager._drain_inbox(record))
    try:
        await entered.wait()
        second = await manager.send(record.status.task_id, parent.key, "Second")
    finally:
        release.set()
    assert await draining == [{"role": "user", "content": "First"}]
    assert record.inbox == [(second["message_id"], "Second")]
    assert record.status.receipts[first["message_id"]] == "delivered"
    assert record.status.receipts[second["message_id"]] == "accepted"
    assert await manager._drain_inbox(record) == [{"role": "user", "content": "Second"}]


async def test_removed_child_during_send_does_not_claim_receipt_was_persisted(live_task, monkeypatch):
    sessions, parent, manager, record, _finish, _execution = live_task
    entered, release = asyncio.Event(), asyncio.Event()
    save = manager.sessions.save

    async def delayed_save(status):
        entered.set()
        await release.wait()
        return await save(status)

    monkeypatch.setattr(manager.sessions, "save", delayed_save)
    sending = asyncio.create_task(manager.send(record.status.task_id, parent.key, "Inspect once"))
    try:
        await entered.wait()
        await sessions.state.delete(record.session.key, expected_generation=record.session.generation)
    finally:
        release.set()
    receipt = await sending
    assert receipt.get("persisted") is False
    assert "resend" in receipt["warning"].lower()
    assert record.inbox == [(receipt["message_id"], "Inspect once")]
    assert await sessions.state.read_header(record.session.key) is None


async def test_removed_child_prevents_inbox_drain_from_claiming_delivery(live_task):
    sessions, parent, manager, record, _finish, _execution = live_task
    receipt = await manager.send(record.status.task_id, parent.key, "Retain this body")
    await sessions.state.delete(record.session.key, expected_generation=record.session.generation)
    with pytest.raises(SubagentSessionError, match="could not be saved"):
        await manager._drain_inbox(record)
    assert record.inbox == [(receipt["message_id"], "Retain this body")]
    assert record.status.receipts[receipt["message_id"]] == "accepted"


async def test_removed_child_does_not_look_like_successfully_saved_task_completion(live_task):
    sessions, _parent, manager, record, finish, execution = live_task
    await sessions.state.delete(record.session.key, expected_generation=record.session.generation)
    finish.set()
    await execution
    assert record.status.state == "error"
    assert record.status.stop_reason == "persistence_failed"
    assert record.status.partial
    assert record.status.result == "Local fixture result"
    assert manager.bus.inbound.empty()
    assert await sessions.state.read_header(record.session.key) is None


async def test_removed_queued_child_does_not_start_model_or_tool_execution(live_task):
    sessions, parent, manager, _record, _finish, _execution = live_task
    slots = manager._run_slots = asyncio.Semaphore(0)
    execute = manager.execution.run = AsyncMock(return_value=SubagentOutcome("done", "Must not execute"))
    record = await manager._create_task(
        "Queued local fixture", None, "websocket", "inbox", parent.key, None, None,
        None, SimpleNamespace(), announce=True, origin_turn_id=None, session_policy=None,
    )
    execution = manager._running_tasks[record.status.task_id]
    try:
        await sessions.state.delete(record.session.key, expected_generation=record.session.generation)
    finally:
        slots.release()
    await execution
    execute.assert_not_awaited()
    assert record.status.state == "error"
    assert record.status.stop_reason == "persistence_failed"
    assert await sessions.state.read_header(record.session.key) is None


async def test_inline_task_with_removed_child_returns_explicit_save_error(live_task):
    sessions, parent, manager, _record, _finish, _execution = live_task

    async def execute(record):
        await sessions.state.delete(record.session.key, expected_generation=record.session.generation)
        return SubagentOutcome("done", "Retain this verified result")

    manager.execution.run = execute
    response = await manager.run_inline(
        "Inspect fixture", origin_channel="websocket", origin_chat_id="inbox",
        session_key=parent.key, runtime=SimpleNamespace(),
    )
    assert is_tool_error_result(response)
    assert "status could not be saved" in response
    assert "Retain this verified result" in response


async def test_replaced_child_rejects_old_task_status_without_overwriting_new_generation(live_task):
    sessions, _parent, manager, record, _finish, _execution = live_task
    await sessions.state.reset(record.session.key)
    replacement = await sessions.state.read_header(record.session.key)
    assert replacement.generation != record.session.generation
    record.status.result = "Old-generation finding"
    with pytest.raises(SubagentSessionError, match="could not be saved"):
        await manager._save_status(record.status)
    after = await sessions.state.read_header(record.session.key)
    assert after.generation == replacement.generation
    assert after.revision == replacement.revision
    assert after.metadata == replacement.metadata


async def test_task_completion_does_not_publish_into_replaced_child(live_task):
    sessions, parent, manager, record, finish, execution = live_task
    await sessions.state.reset(record.session.key)
    replacement = await sessions.state.read_header(record.session.key)
    finish.set()
    await execution
    after = await sessions.state.read_header(record.session.key)
    assert after.metadata == replacement.metadata
    assert after.revision == replacement.revision
    assert record.status.stop_reason == "persistence_failed"
    assert manager.bus.inbound.empty()
    with pytest.raises(SubagentControlError, match="unavailable"):
        manager.check(record.status.task_id, parent.key)
