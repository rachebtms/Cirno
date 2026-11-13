"""Cross-conversation controls use role checks, saved state and worker ownership."""

import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.selection import conversation_tools
from cirno_core.bus.input_origin import input_origin
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.providers.generation import GenerationSettings
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_handles import SessionHandleResolver


@pytest.fixture
async def supervision(tmp_path):
    set_instance_path(tmp_path)
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "state/sessions")
    source = await sessions.state.get(ROUTER_SESSION_KEY)
    target = await sessions.state.get("websocket:worker")
    await sessions.state.update_metadata(target.key, {"webui": True})
    provider = MagicMock(aclose=AsyncMock())
    provider.generation = GenerationSettings()
    provider.get_default_model.return_value = "test"
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path / "workspace", session_manager=sessions)
    admitted = AsyncMock()
    loop.dispatch.enqueue_locked = admitted
    handle = await SessionHandleResolver(sessions).ahandle_for_session(target.key)
    context = RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key=source.key, session_generation=source.generation)
    with request_context(context):
        yield loop, sessions, "@" + handle.name, admitted, context
    await loop.aclose()
    set_instance_path(None)


async def goal(sessions):
    return (await sessions.state.read_metadata("websocket:worker"))["metadata"].get("goal_state")


@pytest.mark.parametrize("state", ["active", "waiting", "paused", "blocked", "stopped"])
async def test_list_includes_idle_workers_with_unfinished_goals(supervision, state):
    loop, sessions, _, _, _ = supervision
    goal_state = {"goal_id": "work", "status": state, "objective": "Read papers", "wake_at": "2030-01-01T00:00:00Z"}
    await sessions.state.update_metadata("websocket:worker", {"goal_state": goal_state})
    result = json.loads(await loop.tools.get("control_session").execute(action="list"))
    worker = next(row for row in result["conversations"] if row["session_key"] == "websocket:worker")
    assert worker["execution_status"] == "idle"
    assert worker["goal"] == goal_state
    await sessions.state.update_metadata("websocket:worker", {"goal_state": {**goal_state, "status": "completed"}})
    done = json.loads(await loop.tools.get("control_session").execute(action="list"))
    assert not any(row["session_key"] == "websocket:worker" for row in done["conversations"])


async def test_controls_are_hidden_from_ordinary_and_ptc_conversations(supervision):
    loop, _, _, _, _ = supervision
    for ptc in (False, True):
        regular = conversation_tools(loop.tools, "websocket:worker", ptc_mode=ptc)
        cirno = conversation_tools(loop.tools, ROUTER_SESSION_KEY, ptc_mode=ptc)
        if not ptc:
            assert "control_session" not in regular.tool_names
            assert "control_goal" not in regular.tool_names
            assert "control_session" in cirno.tool_names
            assert "control_goal" in cirno.tool_names
        else:
            assert "conversations__control" not in regular.model_instructions()
            assert "goals__control" not in regular.model_instructions()


async def test_router_receives_ordinary_execution_but_delegates_to_durable_workers(supervision):
    loop, _, _, _, _ = supervision
    ordinary = conversation_tools(loop.tools, "websocket:worker")
    cirno = conversation_tools(loop.tools, ROUTER_SESSION_KEY)
    assert {"exec", "write_file", "edit_file", "node"} <= set(ordinary.tool_names)
    assert set(ordinary.tool_names) - {"subagent"} <= set(cirno.tool_names)
    assert "subagent" in ordinary.tool_names
    assert "subagent" not in cirno.tool_names
    assert "message" not in ordinary.tool_names
    assert "message" in cirno.tool_names
    ptc = conversation_tools(loop.tools, ROUTER_SESSION_KEY, ptc_mode=True)
    assert {"exec", "write_file", "edit_file", "node", "message", "project"} <= set(ptc.native.tool_names)
    assert "subagent" not in ptc.native.tool_names
    instructions = ptc.model_instructions()
    assert "shell.exec" in instructions and "nodes.execute" in instructions


async def test_direct_tool_and_service_calls_reject_non_cirno_and_stale_source(supervision):
    loop, _, handle, _, context = supervision
    for source in (replace(context, session_key="websocket:worker"), replace(context, session_generation="cleared")):
        with request_context(source):
            result = await loop.tools.get("control_session").execute(to=handle, action="stop")
            assert result.is_error
            result = await loop.conversation_control.execute(handle, "stop")
            assert result.is_error
            for action, values in (("get", {}), ("configure", {"ptc_mode": True})):
                assert (await loop.tools.get("control_session").execute(to=handle, action=action, **values)).is_error
                assert (await loop.conversation_control.execute(handle, action, **values)).is_error
    assert (await loop.tools.get("control_session").execute(to="@cirno", action="stop")).is_error


async def test_get_configuration_is_read_only_and_lists_model_presets(supervision):
    loop, sessions, handle, admitted, _ = supervision
    before = await sessions.state.read_metadata("websocket:worker")
    result = json.loads(await loop.tools.get("control_session").execute(to=handle, action="get"))
    assert result["workspace_scope"]["project_path"] == str(loop.workspace)
    assert result["model_preset"] == "default"
    assert result["available_model_presets"] == ["default"]
    assert result["ptc_mode"] is False
    assert (await sessions.state.read_metadata("websocket:worker"))["metadata"] == before["metadata"]
    admitted.assert_not_awaited()


async def test_configure_persists_worker_settings_preserving_history_goal_and_access(supervision, tmp_path):
    from cirno_core.bus.outbound_events import SessionUpdatedEvent
    from cirno_core.config.models import ModelPresetConfig
    from cirno_core.security.workspace_access import build_workspace_scope
    from cirno_core.session.model_selection import SESSION_MODEL_PRESET_METADATA_KEY

    loop, sessions, handle, admitted, _ = supervision
    key = "websocket:worker"
    loop.workspace.mkdir(exist_ok=True)
    old_file = loop.workspace / "existing.txt"
    old_file.write_text("Keep this file in the old workspace")
    new_workspace = tmp_path / "another-workspace"
    new_workspace.mkdir()
    loop.runtime_resolver._model_presets["Research"] = ModelPresetConfig(model="research-model")
    await sessions.state.import_messages(key, [{"role": "user", "content": "Original task"}, {"role": "assistant", "content": "Saved progress"}])
    metadata = {"workspace_scope": build_workspace_scope(loop.workspace, "review").payload(), "project_id": "same-project",
                "goal_state": {"goal_id": "g", "status": "stopped", "objective": "Finish task"}, "_sustained_goal_continuation_rounds": 3}
    await sessions.state.update_metadata(key, metadata)

    result = json.loads(await loop.tools.get("control_session").execute(
        to=handle, action="configure", workspace=str(new_workspace), ptc_mode=True, model_preset="research"))
    assert result["workspace_scope"]["project_path"] == str(new_workspace)
    assert result["workspace_scope"]["access_mode"] == "review"
    assert result["model_preset"] == "Research" and result["ptc_mode"] is True
    assert result["continuation_queued"] is False
    stored = await sessions.state.read(key)
    assert stored.metadata[SESSION_MODEL_PRESET_METADATA_KEY] == "Research"
    for name, value in metadata.items():
        if name != "workspace_scope":
            assert stored.metadata[name] == value
    assert [message["content"] for message in stored.messages] == ["Original task", "Saved progress"]
    assert old_file.read_text() == "Keep this file in the old workspace"
    assert not (new_workspace / old_file.name).exists()
    assert (await loop.runtime_for_session(stored)).model == "research-model"
    assert loop.llm_runtime().model == "test"
    selected_tools = conversation_tools(loop.tools, key, ptc_mode=stored.metadata["ptc_mode"])
    assert "control_session" not in selected_tools.tool_names
    assert "conversations__control" not in selected_tools.model_instructions()
    assert stored.metadata["supervision_events"][-1]["source"] == "@cirno"
    events = [await asyncio.wait_for(loop.bus.consume_outbound(), 1) for _ in range(loop.bus.outbound_size)]
    update = next(message.event for message in events if isinstance(message.event, SessionUpdatedEvent))
    assert update.workspace_scope["project_path"] == str(new_workspace)
    admitted.assert_not_awaited()

    restarted = SessionManager(loop.workspace, sessions_root=tmp_path / "state/sessions")
    restored = await restarted.state.read(key)
    assert restored.metadata["ptc_mode"] is True
    assert restored.metadata[SESSION_MODEL_PRESET_METADATA_KEY] == "Research"
    assert restored.metadata["workspace_scope"]["project_path"] == str(new_workspace)
    await loop.tools.get("control_session").execute(to=handle, action="configure", model_preset="default", ptc_mode=False)
    restored = await sessions.state.read(key)
    assert SESSION_MODEL_PRESET_METADATA_KEY not in restored.metadata
    assert restored.metadata["ptc_mode"] is False
    assert (await loop.runtime_for_session(restored)).model == "test"


@pytest.mark.parametrize("values", [
    {}, {"workspace": "relative/path"}, {"workspace": "/cirno-test-missing-path"},
    {"ptc_mode": "false"}, {"ptc_mode": True, "model_preset": "missing"},
    {"model_preset": ""}, {"access_mode": "full"},
])
async def test_invalid_configuration_is_rejected_without_partial_changes(supervision, values):
    loop, sessions, handle, admitted, _ = supervision
    before = await sessions.state.read_metadata("websocket:worker")
    result = await loop.tools.get("control_session").execute(to=handle, action="configure", **values)
    assert result.is_error
    assert (await sessions.state.read_metadata("websocket:worker"))["metadata"] == before["metadata"]
    admitted.assert_not_awaited()


async def test_running_worker_must_be_stopped_before_configuration(supervision):
    loop, sessions, handle, admitted, _ = supervision
    worker = asyncio.create_task(asyncio.Event().wait())
    loop._track_active_task("websocket:worker", worker)
    await asyncio.sleep(0)
    result = await loop.tools.get("control_session").execute(to=handle, action="configure", ptc_mode=True)
    assert result.is_error and "stop" in result
    assert not worker.done()
    assert "ptc_mode" not in (await sessions.state.read_metadata("websocket:worker"))["metadata"]
    await loop.tools.get("control_session").execute(to=handle, action="stop")
    assert worker.cancelled()
    result = json.loads(await loop.tools.get("control_session").execute(to=handle, action="configure", ptc_mode=True))
    assert result["ptc_mode"] is True
    admitted.assert_not_awaited()
    await loop.tools.get("control_session").execute(to=handle, action="continue")
    admitted.assert_awaited_once()


@pytest.mark.parametrize("queued", [False, True])
async def test_configuration_rejects_pending_or_locked_execution(supervision, queued):
    loop, _, handle, _, _ = supervision
    key = "websocket:worker"
    lock = loop._get_session_lock(key)
    if queued:
        loop._pending_queues[key] = asyncio.Queue()
    else:
        await lock.acquire()
    try:
        result = await loop.conversation_control.execute(handle, "configure", ptc_mode=True)
        assert result.is_error and "running" in result
    finally:
        if lock.locked():
            lock.release()
        loop._pending_queues.pop(key, None)


async def test_stop_cancels_only_target_and_preserves_goal_and_context(supervision):
    loop, sessions, handle, admitted, _ = supervision
    await sessions.state.import_messages("websocket:worker", [{"role": "user", "content": "Original task"}])
    await sessions.state.update_metadata("websocket:worker", {"goal_state": {"goal_id": "g", "status": "active", "objective": "Finish task", "recap": "Part one done"}, "_sustained_goal_continuation_rounds": 3})
    worker = asyncio.create_task(asyncio.Event().wait())
    unrelated = asyncio.create_task(asyncio.Event().wait())
    loop._track_active_task("websocket:worker", worker)
    loop._track_active_task("websocket:other", unrelated)
    await asyncio.sleep(0)
    result = json.loads(await loop.tools.get("control_session").execute(to=handle, action="stop"))
    assert result["cancelled_tasks"] == 1
    assert worker.cancelled() and not unrelated.done()
    assert (await goal(sessions))["status"] == "stopped"
    assert (await goal(sessions))["recap"] == "Part one done"
    session = await sessions.state.read("websocket:worker")
    assert session.messages[0]["content"] == "Original task"
    assert session.metadata["_sustained_goal_continuation_rounds"] == 3
    assert session.metadata["supervision_events"][-1]["source"] == "@cirno"
    history = await sessions.state.project_history(session.key, lambda reader: list(reader.navigation()))
    assert history[-1][2].content["session_message"]["session"]["name"] == "cirno"
    admitted.assert_not_awaited()
    unrelated.cancel()
    await asyncio.gather(unrelated, return_exceptions=True)


async def test_continue_reactivates_goal_and_keeps_original_authorization(supervision):
    loop, sessions, handle, admitted, _ = supervision
    await sessions.state.update_metadata("websocket:worker", {"goal_state": {"goal_id": "g", "status": "stopped", "objective": "Task", "continuation_limit": 5}, "_sustained_goal_continuation_rounds": 4})
    result = json.loads(await loop.tools.get("control_session").execute(to=handle, action="continue"))
    assert result["continuation_queued"]
    message = admitted.await_args.args[0]
    assert message.session_key == "websocket:worker"
    assert message.session_generation == (await sessions.state.read_header(message.session_key)).generation
    assert message.metadata["_internal_continuation"] is True
    assert input_origin(message)["label"] == "@cirno"
    assert (await goal(sessions))["status"] == "active"
    assert (await sessions.state.read_metadata(message.session_key))["metadata"]["_sustained_goal_continuation_rounds"] == 4
    loop._pending_queues[message.session_key] = asyncio.Queue()
    again = json.loads(await loop.tools.get("control_session").execute(to=handle, action="continue"))
    assert again["status"] == "already_running"
    assert admitted.await_count == 1


async def test_goal_controls_reuse_worker_state_and_preserve_limits(supervision):
    loop, sessions, handle, admitted, _ = supervision
    tool = loop.tools.get("control_goal")
    assert (await tool.execute(to=handle, action="create")).is_error
    result = await tool.execute(to=handle, action="create", objective="Verify result", continuation_limit=7)
    assert not getattr(result, "is_error", False)
    original = await goal(sessions)
    assert original["report_to"] == ROUTER_SESSION_KEY
    await sessions.state.update_metadata("websocket:worker", {"_sustained_goal_continuation_rounds": 2})
    await tool.execute(to=handle, action="update", recap="Verified half", ui_summary="Verification", continuation_limit=0)
    changed = await goal(sessions)
    assert changed["goal_id"] == original["goal_id"]
    assert changed["objective"] == "Verify result"
    assert changed["continuation_limit"] == 0
    assert changed["recap"] == "Verified half"
    assert json.loads(await tool.execute(to=handle, action="get"))["continuation_rounds"] == 2
    await tool.execute(to=handle, action="wait", wake_after_seconds=60)
    assert (await goal(sessions))["status"] == "waiting"
    await tool.execute(to=handle, action="stop")
    assert (await goal(sessions))["status"] == "stopped"
    await tool.execute(to=handle, action="resume")
    assert (await goal(sessions))["status"] == "active"
    await tool.execute(to=handle, action="pause")
    assert (await goal(sessions))["status"] == "paused"
    await tool.execute(to=handle, action="set", objective="Replacement task")
    assert (await goal(sessions))["goal_id"] != original["goal_id"]
    assert (await goal(sessions))["objective"] == "Replacement task"
    assert (await goal(sessions))["continuation_limit"] == 0
    assert (await sessions.state.read_metadata("websocket:worker"))["metadata"].get("_sustained_goal_continuation_rounds", 0) == 0
    assert (await tool.execute(to=handle, action="complete")).is_error
    await tool.execute(to=handle, action="delete")
    assert await goal(sessions) is None


async def test_new_input_waits_until_target_control_settles(supervision):
    loop, _, handle, admitted, _ = supervision
    entered, release = asyncio.Event(), asyncio.Event()
    async def cancel(key, **kwargs):
        entered.set()
        await release.wait()
        return 0
    loop.cancel_session_work = cancel
    controlling = asyncio.create_task(loop.conversation_control.execute(handle, "stop"))
    await entered.wait()
    from cirno_core.bus.events import InboundMessage
    incoming = asyncio.create_task(loop.dispatch.enqueue(InboundMessage(channel="websocket", sender_id="owner", chat_id="worker", content="New request")))
    await asyncio.sleep(0)
    admitted.assert_not_awaited()
    release.set()
    await asyncio.gather(controlling, incoming)
    admitted.assert_awaited_once()


async def test_fork_after_supervisory_display_does_not_shift_model_input_boundary(supervision):
    from cirno_core.session.presentation_history import fact_from_record
    from cirno_core.session.model import SessionPolicy
    loop, sessions, handle, _, _ = supervision
    key = "websocket:worker"
    await sessions.state.import_messages(key, [{"role": "user", "content": "First task"}, {"role": "assistant", "content": "First answer"}])
    await sessions.state.set_policy(key, SessionPolicy(log_content=False))
    await sessions.state.append_history(key, [fact_from_record({"event": "user", "text": "First task"}), fact_from_record({"event": "message", "text": "First answer"})], expected_generation=None)
    await loop.conversation_control.execute(handle, "stop")
    await sessions.state.import_messages(key, [{"role": "user", "content": "Second task"}])
    await sessions.state.append_history(key, [fact_from_record({"event": "user", "text": "Second task"})], expected_generation=None)
    fork = await sessions.state.fork(key, "websocket:fork", 1)
    assert [message["content"] for message in fork.messages] == ["First task", "First answer"]
    assert fork.policy.log_content is False
    copied = await sessions.state.project_history(fork.key, lambda reader: list(reader.navigation()))
    assert not any(fact.content.get("text") == "Second task" for _, _, fact in copied)
    assert any(fact.content.get("input_origin", {}).get("kind") == "supervision" for _, _, fact in copied)


async def test_cirno_continue_uses_durable_recovery_path_after_model_failure(supervision):
    from cirno_core.session.recovery.coordinator import RecoveryCoordinator
    from cirno_core.session.recovery.contracts import RECOVERY_METADATA_KEY, RECOVERY_INBOUND_METADATA_KEY
    loop, sessions, handle, admitted, _ = supervision
    loop.recovery_admission = RecoveryCoordinator(sessions, loop.bus)
    await sessions.state.import_messages("websocket:worker", [{"role": "user", "content": "Authorized task"},
                                                          {"role": "assistant", "content": "Saved partial result"}])
    await sessions.state.update_metadata("websocket:worker", {RECOVERY_METADATA_KEY: {
        "status": "awaiting_user", "recovery_id": "api-failure", "reason": "model_request_failed", "can_continue": True,
    }})
    result = json.loads(await loop.tools.get("control_session").execute(to=handle, action="continue"))
    assert result["continuation_queued"]
    message = await loop.bus.consume_inbound()
    assert message.session_key == "websocket:worker"
    assert message.metadata[RECOVERY_INBOUND_METADATA_KEY] == "api-failure"
    restored = await sessions.state.read_header(message.session_key)
    assert restored.metadata[RECOVERY_METADATA_KEY]["status"] == "resuming"
    admitted.assert_not_awaited()  # No generic prompt or duplicate continuation.
    assert await loop.recovery_admission.admit(message)
    await loop.recovery_admission.turn_completed(message.session_key)
    assert (await sessions.state.read_header(message.session_key)).metadata[RECOVERY_METADATA_KEY]["status"] == "recovered"
