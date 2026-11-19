"""Persisted task observations never stand in for live execution resources."""

import json
import time
from unittest.mock import Mock

import pytest
from cirno_core.agent.subagents.contracts import SubagentControlError
from cirno_core.agent.subagents.manager import SubagentManager
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.subagent import SubagentTool
from cirno_core.bus.queue import MessageBus
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import SessionPolicy


@pytest.fixture
async def orphan(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    parent = await sessions.state.get_header("websocket:orphan")
    manager = SubagentManager(tmp_path, MessageBus(), 1000, consolidator=Mock(), session_manager=sessions)
    status = SubagentStatus("fixture-orphan", "Fixture", "Inspect once", time.monotonic(),
                            owner=parent.key, state="running", phase="awaiting_model")
    child = await manager.sessions.create(status)
    try:
        yield sessions, parent, manager, status, child
    finally:
        await manager.close()
        await sessions.state.aclose()


@pytest.mark.parametrize(("action", "state"), [
    ("send", "queued"), ("send", "running"),
    ("cancel", "queued"), ("cancel", "running"), ("cancel", "stopping"),
])
async def test_orphan_control_returns_explanatory_tool_error_without_mutating_saved_status(orphan, action, state):
    sessions, parent, manager, status, child = orphan
    status.state = status.phase = state
    assert await manager.sessions.save(status)
    before = await sessions.state.read_header(child.key)
    with request_context(RequestContext("websocket", "orphan", session_key=parent.key)):
        result = await SubagentTool(manager).execute(action, status.task_id, message="Inspect once")
    assert is_tool_error_result(result)
    assert "live execution" in result
    after = await sessions.state.read_header(child.key)
    assert after.metadata == before.metadata
    assert after.revision == before.revision
    assert manager.get_running_count() == 0


@pytest.mark.parametrize("state", ["done", "cancelled", "interrupted"])
async def test_terminal_task_cancel_remains_idempotent_without_live_resources(orphan, state):
    _sessions, parent, manager, status, _child = orphan
    status.state = status.phase = state
    status.finished_at = time.monotonic()
    status.completed_at = time.time()
    assert await manager.sessions.save(status)
    with request_context(RequestContext("websocket", "orphan", session_key=parent.key)):
        result = await SubagentTool(manager).execute("cancel", status.task_id)
    assert not is_tool_error_result(result)
    assert json.loads(result)["state"] == state


async def test_explicit_host_recovery_seals_orphan_receipts_without_replaying_work(orphan):
    _sessions, parent, manager, status, _child = orphan
    status.receipts = {"queued": "accepted", "already-read": "delivered"}
    assert await manager.sessions.save(status)
    await manager.recover_interrupted()
    saved = manager.check(status.task_id, parent.key)
    assert saved.state == "interrupted"
    assert saved.stop_reason == "host_restarted"
    assert saved.completed_at is not None
    assert saved.receipts == {"queued": "undelivered", "already-read": "delivered"}
    assert manager.get_running_count() == 0
    assert manager.bus.inbound.empty()


async def test_recovery_cannot_overwrite_a_child_replaced_after_its_status_read(orphan, monkeypatch):
    sessions, _parent, manager, _status, child = orphan
    save = manager.sessions.save
    replacement = None

    async def replace_before_save(status):
        nonlocal replacement
        await sessions.state.reset(child.key)
        replacement = await sessions.state.read_header(child.key)
        return await save(status)

    monkeypatch.setattr(manager.sessions, "save", replace_before_save)
    await manager.recover_interrupted()
    after = await sessions.state.read_header(child.key)
    assert replacement is not None
    assert after.generation == replacement.generation
    assert after.metadata == replacement.metadata
    assert after.revision == replacement.revision


async def test_child_generation_is_private_but_fences_an_already_queued_completion(orphan):
    sessions, parent, manager, status, child = orphan
    header = await sessions.state.read_header(child.key)
    assert status.child_generation == child.generation
    assert "child_generation" not in status.as_dict()
    assert "child_generation" not in header.metadata["subagent_task"]
    await manager.reports.announce(status.task_id, "Fixture", "Inspect once", "Verified finding", {
        "channel": "websocket", "chat_id": "orphan", "session_key": parent.key,
        "session_generation": parent.generation,
    }, "ok", child_generation=child.generation)
    message = manager.bus.inbound.get_nowait()
    assert manager.accepts_result(message, parent.key)
    await sessions.state.reset(child.key)
    assert not manager.accepts_result(message, parent.key)


async def test_history_read_rejects_child_replacement_between_status_and_snapshot(orphan, monkeypatch):
    sessions, parent, manager, status, child = orphan
    replacement = sessions.get_existing(child.key)
    replacement.generation = "replacement-generation"
    monkeypatch.setattr(sessions, "get_existing", lambda _key: replacement)
    with pytest.raises(SubagentControlError, match="unavailable"):
        manager.read_session(status.task_id, parent.key)


async def test_transient_child_status_is_bound_without_creating_a_database_session(orphan):
    sessions, parent, manager, _status, _child = orphan
    status = SubagentStatus("transient-child", "Fixture", "Private task", time.monotonic(), owner=parent.key)
    child = await manager.sessions.create(status, policy=SessionPolicy(persist=False))
    assert sessions.read_session_version(child.key) is None
    status.phase = "awaiting_model"
    assert await manager.sessions.save(status)
    assert manager.sessions.status(status.task_id, parent.key).child_generation == child.generation
    await sessions.state.reset(child.key)
    replacement = await sessions.state.read_header(child.key)
    assert not await manager.sessions.save(status)
    after = await sessions.state.read_header(child.key)
    assert after.metadata == replacement.metadata
    assert sessions.read_session_version(child.key) is None
