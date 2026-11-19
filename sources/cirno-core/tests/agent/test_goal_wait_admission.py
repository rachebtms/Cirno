"""Unrepresentable waits are refused before stopping a running Worker."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.conversation_control import ConversationControl
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.long_task import UpdateGoalTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.supervision import ControlGoalTool
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import GoalStateChanged
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_handles import SessionHandleResolver


@pytest.fixture
async def waiting_control(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    source = await sessions.state.get_header(ROUTER_SESSION_KEY)
    target = await sessions.state.get_header("websocket:worker")
    goal = {
        "goal_id": "fixture",
        "status": "active",
        "objective": "Keep working",
        "recap": "Verified progress",
    }
    await sessions.state.update_metadata(target.key, {"goal_state": goal, "webui": True})
    handle = await SessionHandleResolver(sessions).ahandle_for_session(target.key)
    intake, execution = asyncio.Lock(), asyncio.Lock()
    loop = SimpleNamespace(
        sessions=sessions,
        bus=MessageBus(),
        goal_continuation_limit=0,
        session_intake_lock=lambda _key: intake,
        _get_session_lock=lambda _key: execution,
        cancel_session_work=AsyncMock(return_value=0),
        dispatch=SimpleNamespace(is_running=lambda _key: False, enqueue_locked=AsyncMock()),
    )
    registry = ToolRegistry()
    registry.register(ControlGoalTool(ConversationControl(loop)))
    registry.register(UpdateGoalTool(sessions, loop.bus))
    try:
        yield loop, registry, source, target, handle, goal
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("operation", ["supervisor", "self"])
async def test_overflowing_goal_wait_has_no_execution_or_metadata_effect(
    waiting_control, operation
):
    loop, registry, source, target, handle, goal = waiting_control
    owner = source if operation == "supervisor" else target
    params = {"action": "wait", "wake_after_seconds": 10**12}
    if operation == "supervisor":
        params["to"] = handle.id
    with request_context(
        RequestContext(
            channel="websocket",
            chat_id=ROUTER_CHAT_ID if operation == "supervisor" else "worker",
            session_key=owner.key,
            session_generation=owner.generation,
        )
    ):
        result = await registry.execute(
            "goals__control" if operation == "supervisor" else "goals__update", params
        )
    assert getattr(result, "is_error", False)
    loop.cancel_session_work.assert_not_awaited()
    loop.dispatch.enqueue_locked.assert_not_awaited()
    assert "supported date range" in result
    metadata = (await loop.sessions.state.read_metadata(target.key))["metadata"]
    assert metadata["goal_state"] == goal


@pytest.mark.parametrize("operation", ["supervisor", "self"])
@pytest.mark.parametrize("delay", [1, 10_000_000])
async def test_valid_wait_preserves_progress_and_records_a_utc_deadline(
    waiting_control, operation, delay
):
    loop, registry, source, target, handle, goal = waiting_control
    owner = source if operation == "supervisor" else target
    params = {"action": "wait", "wake_after_seconds": delay}
    if operation == "supervisor":
        params["to"] = handle.id
    before = datetime.now(timezone.utc)
    with request_context(
        RequestContext(
            channel="websocket",
            chat_id=ROUTER_CHAT_ID if operation == "supervisor" else "worker",
            session_key=owner.key,
            session_generation=owner.generation,
        )
    ):
        result = await registry.execute(
            "goals__control" if operation == "supervisor" else "goals__update", params
        )
    after = datetime.now(timezone.utc)
    assert not getattr(result, "is_error", False), result
    saved = (await loop.sessions.state.read_metadata(target.key))["metadata"]["goal_state"]
    assert saved["goal_id"] == goal["goal_id"]
    assert saved["status"] == "waiting"
    assert saved["recap"] == goal["recap"]
    assert (
        before + timedelta(seconds=delay)
        <= datetime.fromisoformat(saved["wake_at"])
        <= after + timedelta(seconds=delay)
    )
    loop.dispatch.enqueue_locked.assert_not_awaited()


@pytest.mark.parametrize("recap", [None, "", "New verified progress"])
async def test_continue_distinguishes_omitted_recap_from_explicit_replacement(
    waiting_control, recap
):
    loop, registry, _source, target, _handle, goal = waiting_control
    params = {"action": "continue", **({"recap": recap} if recap is not None else {})}
    with request_context(
        RequestContext(
            channel="websocket",
            chat_id="worker",
            session_key=target.key,
            session_generation=target.generation,
        )
    ):
        result = await registry.execute("goals__update", params)
    assert not getattr(result, "is_error", False), result
    saved = (await loop.sessions.state.read_metadata(target.key))["metadata"]["goal_state"]
    assert saved["recap"] == (goal["recap"] if recap is None else recap)
    assert saved["status"] == "active" and saved["goal_id"] == goal["goal_id"]


async def test_self_goal_change_event_carries_the_committed_generation(waiting_control):
    loop, registry, _source, target, _handle, _goal = waiting_control
    events = []
    unsubscribe = loop.bus.subscribe(events.append, GoalStateChanged)
    try:
        # SDK callers may omit a generation; use the committed header identity.
        with request_context(
            RequestContext(
                channel="websocket",
                chat_id="worker",
                session_key=target.key,
            )
        ):
            result = await registry.execute("goals__update", {"action": "continue"})
        assert not getattr(result, "is_error", False), result
        assert len(events) == 1
        assert events[0].context.session_generation == target.generation
    finally:
        unsubscribe()
