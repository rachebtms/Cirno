"""Child task results remain bound to the parent generation that created them."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.execution.dispatch import SessionDispatcher
from cirno_core.agent.subagents.contracts import SubagentControlError, SubagentOutcome
from cirno_core.agent.subagents.manager import SubagentManager
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.subagent import SubagentTool
from cirno_core.bus.events import INBOUND_META_TURN_ID
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import RuntimeEventContext, SubagentTaskChanged
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import SessionPolicy
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator


@pytest.fixture
async def parent_task(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    parent = await sessions.state.get_header("websocket:parent")
    bus = MessageBus()
    manager = SubagentManager(
        tmp_path / "workspace", bus, 1000, consolidator=Mock(), session_manager=sessions,
    )
    status = SubagentStatus("fixture-task", "Fixture task", "Inspect saved files", time.monotonic(), owner=parent.key)
    child = await manager.sessions.create(status)
    try:
        yield sessions, parent, manager, bus, child
    finally:
        await manager.close()
        await sessions.state.aclose()


def origin(parent):
    return {"channel": "websocket", "chat_id": "parent", "session_key": parent.key,
            "session_generation": parent.generation}


async def test_child_creation_records_parent_generation_atomically(parent_task):
    _sessions, parent, _manager, _bus, child = parent_task
    assert child.metadata.get("parent_session_generation") == parent.generation


async def test_queued_completion_is_rejected_after_parent_reset(parent_task):
    sessions, parent, manager, bus, _child = parent_task
    await manager.reports.announce("fixture-task", "Fixture", "Inspect saved files", "Old result", origin(parent), "ok")
    message = bus.inbound.get_nowait()
    assert message.session_generation == parent.generation
    await sessions.state.reset(parent.key)
    agent = SimpleNamespace(
        lifecycle=SimpleNamespace(check_admission=Mock()), sessions=sessions,
        _pending_queues={}, commands=SimpleNamespace(is_priority=lambda _text: False),
        _automation_turn_coordinators=[], runtime_event_publisher=SimpleNamespace(user_input_accepted=AsyncMock()),
    )
    dispatcher = SessionDispatcher(agent)
    dispatcher.enqueue = AsyncMock()
    await dispatcher.receive(message)
    dispatcher.enqueue.assert_not_awaited()


async def test_reset_hides_old_child_status_and_history_without_deleting_data(parent_task):
    sessions, parent, manager, _bus, child = parent_task
    assert manager.check("fixture-task", parent.key).task_id == "fixture-task"
    await sessions.state.reset(parent.key)
    with pytest.raises(SubagentControlError, match="unavailable"):
        manager.check("fixture-task", parent.key)
    assert manager.sessions.snapshot("fixture-task", parent.key) is None
    assert manager.statuses_for_session(parent.key) == {}
    assert await manager.read_statuses_for_session(parent.key) == {}
    assert await sessions.state.read_header(child.key) is not None


async def test_replacement_accepts_new_bound_tasks(parent_task):
    sessions, parent, manager, bus, _child = parent_task
    await sessions.state.reset(parent.key)
    current = await sessions.state.read_header(parent.key)
    status = SubagentStatus("replacement-task", "New task", "New local fixture", time.monotonic(), owner=parent.key)
    await manager.sessions.create(status)
    assert manager.check(status.task_id, parent.key).task_id == status.task_id
    await manager.reports.announce(status.task_id, "New task", "New local fixture", "Done", origin(current), "ok")
    message = bus.inbound.get_nowait()
    assert message.session_generation == current.generation
    assert manager.accepts_result(message, current.key)


@pytest.mark.parametrize("failure", ["transcript", "status", "both"])
async def test_terminal_save_failure_still_reports_failure_and_retains_output(parent_task, monkeypatch, failure):
    _sessions, parent, manager, bus, _child = parent_task
    manager.execution.run = AsyncMock(return_value=SubagentOutcome("done", "Verified local finding"))
    if failure in {"transcript", "both"}:
        save_history = manager._save_transcript

        async def save_transcript(record):
            if record.status.finished_at is not None:
                raise OSError("Fixture terminal write failure")
            await save_history(record)

        monkeypatch.setattr(manager, "_save_transcript", save_transcript)
    if failure in {"status", "both"}:
        save_metadata = manager.sessions.save

        async def save_status(status):
            if status.completed_at is not None:
                raise OSError("Fixture terminal write failure")
            return await save_metadata(status)

        monkeypatch.setattr(manager.sessions, "save", save_status)
    record = await manager._create_task(
        "Inspect fixture", None, "websocket", "parent", parent.key, None, None,
        None, SimpleNamespace(), announce=True, origin_turn_id=None, session_policy=None,
    )
    execution = manager._running_tasks[record.status.task_id]
    await execution
    await asyncio.sleep(0)
    status = manager.check(record.status.task_id, parent.key)
    assert status.state == "error"
    assert status.stop_reason == "persistence_failed"
    assert status.result == "Verified local finding"
    assert status.partial
    report = bus.inbound.get_nowait()
    assert report.metadata["subagent_state"] == "error"
    assert report.metadata["subagent_partial"] is True
    assert "Verified local finding" in report.content
    assert "saved" in report.content.lower()
    if failure == "transcript":
        assert manager.sessions.status(status.task_id, parent.key).state == "error"
    if failure == "both":
        assert "history and status" in report.content


async def test_inline_task_returns_save_failure_as_tool_error(parent_task, monkeypatch):
    _sessions, parent, manager, bus, _child = parent_task
    manager.execution.run = AsyncMock(return_value=SubagentOutcome("done", "Verified finding"))
    save = manager.sessions.save

    async def save_status(status):
        if status.completed_at is not None:
            raise OSError("Fixture terminal write failure")
        return await save(status)

    monkeypatch.setattr(manager.sessions, "save", save_status)
    result = await manager.run_inline(
        "Inspect fixture", origin_channel="websocket", origin_chat_id="parent",
        session_key=parent.key, runtime=SimpleNamespace(),
    )
    assert is_tool_error_result(result)
    assert "status could not be saved" in result
    assert "Verified finding" in result
    assert bus.inbound.empty()


async def test_retired_parent_does_not_receive_a_new_child_announcement(parent_task):
    sessions, parent, manager, bus, _child = parent_task
    await sessions.state.reset(parent.key)
    await manager.reports.announce("fixture-task", "Fixture", "Inspect saved files", "Old result", origin(parent), "ok")
    assert bus.inbound.empty()


async def test_old_task_status_event_does_not_refresh_replaced_parent(parent_task):
    sessions, parent, _manager, bus, _child = parent_task
    coordinator = WebuiTurnCoordinator(bus, sessions, lambda _work: None)
    unsubscribe = coordinator.subscribe()
    try:
        await sessions.state.reset(parent.key)
        await bus.publish(SubagentTaskChanged(
            context=RuntimeEventContext(
                channel="websocket", chat_id="parent", session_key=parent.key,
                session_generation=parent.generation,
            ), task_id="fixture-task",
        ))
        assert bus.outbound.empty()
    finally:
        unsubscribe()


async def test_real_admission_and_completion_keep_committed_parent_identity(parent_task, monkeypatch):
    sessions, parent, manager, bus, _child = parent_task
    release = asyncio.Event()
    events = []
    unsubscribe = bus.subscribe(lambda event: events.append(event), SubagentTaskChanged)

    async def execute(_record):
        await release.wait()
        return SubagentOutcome("done", "Verified local fixture")

    monkeypatch.setattr(manager.execution, "run", execute)
    try:
        record = await manager._create_task(
            "Inspect fixture", None, "websocket", "parent", parent.key, None, None,
            None, SimpleNamespace(), announce=True, origin_turn_id=None, session_policy=None,
        )
        execution = manager._running_tasks[record.status.task_id]
        assert record.origin["session_generation"] == parent.generation
        # A metadata update is the same conversation, not a replacement.
        await sessions.state.update_metadata(parent.key, {"fixture": "new revision"})
        release.set()
        await execution
        await asyncio.sleep(0)
        message = bus.inbound.get_nowait()
        assert message.session_generation == parent.generation
        assert manager.accepts_result(message, parent.key)
        assert events and all(event.context.session_generation == parent.generation for event in events)
        assert manager.read_session(record.status.task_id, parent.key)[0].state == "done"
    finally:
        release.set()
        unsubscribe()


@pytest.mark.parametrize("with_generation", [True, False])
async def test_current_task_status_event_still_refreshes_parent(parent_task, with_generation):
    sessions, parent, _manager, bus, _child = parent_task
    coordinator = WebuiTurnCoordinator(bus, sessions, lambda _work: None)
    unsubscribe = coordinator.subscribe()
    try:
        event = SubagentTaskChanged(context=RuntimeEventContext(
            channel="websocket", chat_id="parent", session_key=parent.key,
            session_generation=parent.generation if with_generation else None,
        ), task_id="fixture-task")
        await bus.publish(event)
        assert bus.outbound.get_nowait().event == event
    finally:
        unsubscribe()


async def test_persistent_binding_survives_cache_disposal(parent_task):
    sessions, parent, manager, _bus, _child = parent_task
    sessions.state.forget_transient(parent.key)
    assert manager.sessions.contains("fixture-task", parent.key)
    await sessions.state.reset(parent.key)
    sessions.state.forget_transient(parent.key)
    assert manager.sessions.status("fixture-task", parent.key) is None


async def test_transient_parent_binding_does_not_require_a_database_row(parent_task):
    sessions, _parent, manager, _bus, _child = parent_task
    parent = await sessions.state.register_transient("sdk:ephemeral")
    status = SubagentStatus("private-task", "Private", "Local fixture", time.monotonic(), owner=parent.key)
    child = await manager.sessions.create(status, policy=SessionPolicy(persist=False, log_content=False))
    assert not child.policy.persist
    assert sessions.read_session_version(parent.key) is None
    assert manager.check(status.task_id, parent.key).task_id == status.task_id
    await sessions.state.reset(parent.key)
    with pytest.raises(SubagentControlError, match="unavailable"):
        manager.check(status.task_id, parent.key)
    assert await sessions.state.read_header(child.key) is not None


@pytest.mark.parametrize("action", ["check", "send", "cancel"])
async def test_public_task_controls_reject_replaced_parent(parent_task, action):
    sessions, parent, manager, _bus, _child = parent_task
    await sessions.state.reset(parent.key)
    with request_context(RequestContext("websocket", "parent", session_key=parent.key)):
        result = await SubagentTool(manager).execute(action, "fixture-task", message="Follow-up")
    assert is_tool_error_result(result)
    assert "task unavailable" in result


@pytest.mark.parametrize("replacement", ["reset", "edit"])
@pytest.mark.parametrize("cached", [True, False])
async def test_legacy_child_is_readable_until_parent_history_is_replaced(parent_task, replacement, cached):
    sessions, parent, manager, _bus, child = parent_task
    await sessions.state.update_metadata(child.key, {}, remove=["parent_session_generation"])
    assert manager.check("fixture-task", parent.key).task_id == "fixture-task"
    await sessions.state.import_messages(parent.key, [{
        "role": "user", "content": "Original task", INBOUND_META_TURN_ID: "saved-input",
    }])
    if replacement == "edit":
        await sessions.state.edit_user_input(parent.key, "saved-input", "Revised task")
    else:
        await sessions.state.reset(parent.key)
    if not cached:
        sessions.state.forget_transient(parent.key)
        sessions.state.forget_transient(child.key)
    with pytest.raises(SubagentControlError, match="unavailable"):
        manager.check("fixture-task", parent.key)
    assert manager.statuses_for_session(parent.key) == {}
    assert await sessions.state.read_header(child.key) is not None
