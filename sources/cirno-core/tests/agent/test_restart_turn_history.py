"""Restart retains every completed round and does not bypass recovery admission."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.execution.checkpoints import RuntimeCheckpointWriter
from cirno_core.agent.goals.scheduler import wake_due_goals
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.generation import GenerationSettings
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import RECOVERY_METADATA_KEY, RUNTIME_CHECKPOINT_KEY
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.summary import SessionSummaryCheckpoint
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy


async def test_restart_recovers_all_tool_rounds_without_repeating_completed_work(tmp_path):
    bus = MessageBus()
    sessions = SessionManager(tmp_path)
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "fixture-model"
    provider.generation = GenerationSettings()
    provider.can_resume_conversation_state.return_value = False
    entered = asyncio.Event()
    requests = []
    for index in range(3):
        (tmp_path / f"{index}.txt").write_text(f"Evidence from round {index}")

    async def respond(**kwargs):
        requests.append(deepcopy(kwargs["messages"]))
        index = len(requests) - 1
        if index < 3:
            return LLMResponse(content=f"Inspecting source {index}", tool_calls=[ToolCallRequest(
                f"read-{index}", "read_file", {"path": str(tmp_path / f"{index}.txt")},
            )])
        entered.set()
        await asyncio.Event().wait()

    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    recovery = RecoveryCoordinator(sessions, bus)
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="fixture-model",
                     session_manager=sessions, recovery_admission=recovery,
                     turn_delivery_factory=TurnDeliveryFactory(bus, WebuiTurnRoutePolicy(sessions)))
    coordinator = WebuiTurnCoordinator(bus, sessions, loop.schedule_background, recovery=recovery)
    request = InboundMessage(channel="websocket", sender_id="user", chat_id="research",
                             content="Inspect all three sources", metadata={"webui": True, "webui_turn_id": "research-turn"})
    try:
        with coordinator.connected():
            await loop.dispatch.receive(request)
            await asyncio.wait_for(entered.wait(), 5)
            loop.preserve_inflight_turns_on_shutdown()
    finally:
        await loop.aclose()

    reopened = SessionManager(tmp_path)
    resumed_bus = MessageBus()
    restart = RecoveryCoordinator(reopened, resumed_bus)
    try:
        await restart.scan()
        restored = await reopened.state.get(request.session_key)
        assert [row["tool_call_id"] for row in restored.messages if row["role"] == "tool"] == [
            "read-0", "read-1", "read-2",
        ]
        for index in range(3):
            assert any(f"Evidence from round {index}" in str(row.get("content")) for row in restored.messages)
        assert resumed_bus.inbound.empty()
        state = restored.metadata[RECOVERY_METADATA_KEY]
        await restart.handle_action("continue", {"chat_id": "research", "recovery_id": state["recovery_id"]})
        resumed_request = resumed_bus.inbound.get_nowait()
        provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content="All evidence verified"))
        resumed_loop = AgentLoop(bus=resumed_bus, provider=provider, workspace=tmp_path,
                                 model="fixture-model", session_manager=reopened, recovery_admission=restart,
                                 turn_delivery_factory=TurnDeliveryFactory(resumed_bus, WebuiTurnRoutePolicy(reopened)))
        resumed_coordinator = WebuiTurnCoordinator(resumed_bus, reopened, resumed_loop.schedule_background, recovery=restart)
        try:
            with resumed_coordinator.connected():
                await resumed_loop.dispatch.execute(resumed_request, asyncio.Queue())
            sent = provider.chat_stream_with_retry.await_args.kwargs["messages"]
            assert sent[0] == requests[0][0], "restart must not rewrite the shared prompt prefix"
            assert [row["tool_call_id"] for row in sent if row["role"] == "tool"] == ["read-0", "read-1", "read-2"]
            final = await reopened.state.get(request.session_key)
            assert isinstance(final.messages[-1]["latency_ms"], int)
            assert [row["tool_call_id"] for row in final.messages if row["role"] == "tool"] == ["read-0", "read-1", "read-2"]
            provider.chat_stream_with_retry.assert_awaited_once()
        finally:
            await resumed_loop.aclose()
    finally:
        await reopened.state.aclose()


@pytest.mark.parametrize("status", ["awaiting_user", "failed", "resuming"])
@pytest.mark.parametrize("goal_status", ["active", "waiting"])
@pytest.mark.parametrize("limit", [0, 7])
async def test_goal_scheduler_respects_recovery_without_consuming_rounds(tmp_path, status, goal_status, limit):
    sessions = SessionManager(tmp_path)
    key = "websocket:research"
    await sessions.state.get(key)
    goal = {"goal_id": "original", "objective": "Verify evidence", "status": goal_status,
            "recap": "Three sources verified", "continuation_limit": limit,
            "wake_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
    await sessions.state.update_metadata(key, {"goal_state": goal, "_sustained_goal_continuation_rounds": 7,
                                               RECOVERY_METADATA_KEY: {"status": status, "recovery_id": "interruption"}})
    loop = SimpleNamespace(sessions=sessions, _pending_queues={}, _discarding_sessions=set(),
                           goal_continuation_limit=0, dispatch=SimpleNamespace(enqueue=AsyncMock()))
    try:
        await wake_due_goals(loop)
        loop.dispatch.enqueue.assert_not_awaited()
        current = await sessions.state.get(key)
        assert current.metadata["goal_state"] == goal
        assert current.metadata["_sustained_goal_continuation_rounds"] == 7
        await sessions.state.update_metadata(key, {RECOVERY_METADATA_KEY: {"status": "recovered", "recovery_id": "interruption"}})
        await wake_due_goals(loop)
        if limit:
            loop.dispatch.enqueue.assert_not_awaited()
            current = await sessions.state.get(key)
            assert current.metadata["goal_state"]["status"] == "paused"
        else:
            loop.dispatch.enqueue.assert_awaited_once()
    finally:
        await sessions.state.aclose()


async def test_checkpoint_summary_can_cover_an_earlier_already_committed_boundary(tmp_path):
    sessions = SessionManager(tmp_path)
    key = "websocket:consolidated"
    session = await sessions.state.get(key)
    session.add_message("user", "Research")
    await sessions.state.prepare_input(session)
    from cirno_core.agent.execution.persistence import TurnPersistence

    writer = RuntimeCheckpointWriter(TurnPersistence(SimpleNamespace(sessions=sessions)), session,
                                     start=2, input_persisted_early=True)
    messages = [{"role": "system", "content": "Fixed prefix"}, {"role": "user", "content": "Research"}]

    async def save(summary=None):
        await writer({"phase": "final_response", "assistant_message": messages[-1],
                      "completed_tool_results": [], "pending_tool_calls": [],
                      "_transcript": messages, "_summary_checkpoint": summary})

    try:
        messages.extend([{"role": "assistant", "content": "First verified finding"},
                         {"role": "assistant", "content": "Second verified finding"}])
        await save()
        messages.append({"role": "assistant", "content": "Third verified finding"})
        summary = SessionSummaryCheckpoint(summary="Summarized the research request", transcript_boundary=2)
        await save(summary)
        assert session.metadata["_last_summary"]["text"] == summary.summary
        assert [row["content"] for row in session.get_history()] == [
            "First verified finding", "Second verified finding", "Third verified finding",
        ]
        # A newer summary covers the first finding, whose raw position predates
        # the last committed suffix. Filtered rows must not shift the boundary.
        messages.append({"role": "assistant", "content": ""})
        messages.append({"role": "assistant", "content": "Fourth verified finding"})
        newer = SessionSummaryCheckpoint(summary="Request and first finding", transcript_boundary=3)
        await save(newer)
        assert [row["content"] for row in session.get_history()] == [
            "Second verified finding", "Third verified finding", "Fourth verified finding",
        ]
        await save(newer)
        assert len([row for row in session.messages if row.get("_hidden_history")]) == 2
        reopened = SessionManager(tmp_path)
        try:
            persisted = await reopened.state.get(key)
            assert persisted.get_history() == session.get_history()
            assert "_transcript" not in str(persisted.metadata)
        finally:
            await reopened.state.aclose()
    finally:
        await sessions.state.aclose()


async def test_restart_during_batch_retains_completed_results_and_marks_only_pending_calls(tmp_path, monkeypatch):
    bus = MessageBus()
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "fixture-model"
    provider.generation = GenerationSettings()
    provider.can_resume_conversation_state.return_value = False
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content="Inspect two sources", tool_calls=[
        ToolCallRequest("done", "read_file", {"path": str(tmp_path / "done")}),
        ToolCallRequest("pending", "read_file", {"path": str(tmp_path / "pending")}),
    ]))
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="fixture-model")
    loop.turn_delivery_factory = TurnDeliveryFactory(bus, WebuiTurnRoutePolicy(loop.sessions))
    coordinator = WebuiTurnCoordinator(bus, loop.sessions, loop.schedule_background)
    persisted, waiting = asyncio.Event(), asyncio.Event()

    async def read(path, **_kwargs):
        if path.endswith("done"):
            return "Completed observation must survive"
        waiting.set()
        await asyncio.Event().wait()

    checkpoint = loop.persistence.checkpoint

    async def observe(session, payload, **kwargs):
        await checkpoint(session, payload, **kwargs)
        if payload.get("completed_tool_results"):
            persisted.set()

    monkeypatch.setattr(loop.tools.get("read_file"), "execute", read)
    monkeypatch.setattr(loop.persistence, "checkpoint", observe)
    request = InboundMessage(channel="websocket", sender_id="user", chat_id="batch",
                             content="Inspect both sources", metadata={"webui": True, "webui_turn_id": "batch-turn"})
    try:
        with coordinator.connected():
            await loop.dispatch.receive(request)
            await asyncio.wait_for(asyncio.gather(persisted.wait(), waiting.wait()), 5)
            loop.preserve_inflight_turns_on_shutdown()
    finally:
        await loop.aclose()
    sessions = SessionManager(tmp_path)
    try:
        before = await sessions.state.get(request.session_key)
        assert [row["tool_call_id"] for row in before.metadata[RUNTIME_CHECKPOINT_KEY]["completed_tool_results"]] == ["done"]
        await RecoveryCoordinator(sessions, MessageBus()).scan()
        restored = await sessions.state.get(request.session_key)
        results = {row["tool_call_id"]: row for row in restored.messages if row["role"] == "tool"}
        assert results["done"]["content"] == "Completed observation must survive"
        assert not results["done"].get("_recovery_interrupted")
        assert results["pending"]["_recovery_interrupted"]
        assert restored.metadata[RECOVERY_METADATA_KEY]["reason"] == "tool_state_unknown"
    finally:
        await sessions.state.aclose()


async def test_restart_preserves_completed_output_segments_without_marking_task_finished(tmp_path):
    bus = MessageBus()
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "fixture-model"
    provider.generation = GenerationSettings()
    provider.can_resume_conversation_state.return_value = False
    entered = asyncio.Event()
    calls = 0

    async def generate(**_kwargs):
        nonlocal calls
        calls += 1
        if calls <= 2:
            return LLMResponse(content=f"Verified segment {calls}. ", finish_reason="length")
        entered.set()
        await asyncio.Event().wait()

    provider.chat_stream_with_retry = AsyncMock(side_effect=generate)
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="fixture-model")
    loop.turn_delivery_factory = TurnDeliveryFactory(bus, WebuiTurnRoutePolicy(loop.sessions))
    coordinator = WebuiTurnCoordinator(bus, loop.sessions, loop.schedule_background)
    request = InboundMessage(channel="websocket", sender_id="user", chat_id="segments",
                             content="Explain the findings", metadata={"webui": True, "webui_turn_id": "segments-turn"})
    try:
        with coordinator.connected():
            await loop.dispatch.receive(request)
            await asyncio.wait_for(entered.wait(), 5)
            loop.preserve_inflight_turns_on_shutdown()
    finally:
        await loop.aclose()
    sessions = SessionManager(tmp_path)
    try:
        await RecoveryCoordinator(sessions, MessageBus()).scan()
        restored = await sessions.state.get(request.session_key)
        assert [row["content"] for row in restored.messages if row["role"] == "assistant"] == [
            "Verified segment 1.", "Verified segment 2.",
        ]
        assert restored.metadata[RECOVERY_METADATA_KEY]["status"] == "awaiting_user"
    finally:
        await sessions.state.aclose()
