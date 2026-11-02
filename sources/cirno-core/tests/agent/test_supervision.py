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
from cirno_core.providers.base import GenerationSettings
from cirno_core.session.keys import CIRNO_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_handles import SessionHandleResolver


@pytest.fixture
async def supervision(tmp_path):
    set_instance_path(tmp_path)
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "state/sessions")
    source = await sessions.state.get(CIRNO_SESSION_KEY)
    target = await sessions.state.get("websocket:worker")
    await sessions.state.update_metadata(target.key, {"webui": True})
    provider = MagicMock(aclose=AsyncMock())
    provider.generation = GenerationSettings()
    provider.get_default_model.return_value = "test"
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path / "workspace", session_manager=sessions)
    admitted = AsyncMock()
    loop._enqueue_session_message_unlocked = admitted
    handle = await SessionHandleResolver(sessions).ahandle_for_session(target.key)
    context = RequestContext(channel="websocket", chat_id="global", session_key=source.key, session_generation=source.generation)
    with request_context(context):
        yield loop, sessions, "@" + handle.name, admitted, context
    await loop.aclose()
    set_instance_path(None)


async def goal(sessions):
    return (await sessions.state.read_metadata("websocket:worker"))["metadata"].get("goal_state")


async def test_controls_are_hidden_from_ordinary_and_ptc_conversations(supervision):
    loop, _, _, _, _ = supervision
    for ptc in (False, True):
        regular = conversation_tools(loop.tools, "websocket:worker", ptc_mode=ptc)
        cirno = conversation_tools(loop.tools, CIRNO_SESSION_KEY, ptc_mode=ptc)
        if not ptc:
            assert "control_session" not in regular.tool_names
            assert "control_goal" not in regular.tool_names
            assert "control_session" in cirno.tool_names
            assert "control_goal" in cirno.tool_names
        else:
            assert "conversations__control" not in regular.sdk_prompt()
            assert "goals__control" not in regular.sdk_prompt()


async def test_direct_tool_and_service_calls_reject_non_cirno_and_stale_source(supervision):
    loop, _, handle, _, context = supervision
    for source in (replace(context, session_key="websocket:worker"), replace(context, session_generation="cleared")):
        with request_context(source):
            result = await loop.tools.get("control_session").execute(to=handle, action="stop")
            assert result.is_error
            result = await loop.conversation_control.execute(handle, "stop")
            assert result.is_error
    assert (await loop.tools.get("control_session").execute(to="@cirno", action="stop")).is_error


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
    assert original["report_to"] == CIRNO_SESSION_KEY
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
    loop._cancel_active_tasks = cancel
    controlling = asyncio.create_task(loop.conversation_control.execute(handle, "stop"))
    await entered.wait()
    from cirno_core.bus.events import InboundMessage
    incoming = asyncio.create_task(loop._enqueue_session_message(InboundMessage(channel="websocket", sender_id="owner", chat_id="worker", content="New request")))
    await asyncio.sleep(0)
    admitted.assert_not_awaited()
    release.set()
    await asyncio.gather(controlling, incoming)
    admitted.assert_awaited_once()


async def test_fork_after_supervisory_display_does_not_shift_model_input_boundary(supervision):
    from cirno_core.session.presentation_history import fact_from_record
    from cirno_core.session.manager import SessionPolicy
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
