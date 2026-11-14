"""Coordination contracts: passive facts, explicit attention and durable inbox receipts."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.goals.scheduler import wake_due_goals
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.coordination import (
    CreateSessionTool,
    ReportWorkTool,
    SetSessionTitleTool,
)
from cirno_core.agent.tools.long_task import UpdateGoalTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.selection import conversation_tools
from cirno_core.agent.tools.session_messages import SendSessionMessageTool, SessionMessageError
from cirno_core.agent.work_reports import deliver_work_report, save_work_report
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.pending import pending_followups
from cirno_core.session.sqlite_store import SessionConflictError


@pytest.fixture
async def setup(tmp_path):
    home = tmp_path / "home"
    set_instance_path(home)
    manager = SessionManager(home / "workspace", sessions_root=home / "sessions")
    for key in ("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "websocket:worker"):
        await manager.state.get(key)
    await manager.state.update_metadata("websocket:worker", {
        "delegated_by": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
        "goal_state": {"goal_id": "task-1", "objective": "Verify a result", "status": "active", "report_to": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"},
    })
    bus = MessageBus()
    yield home, manager, bus
    await manager.state.aclose()
    set_instance_path(None)


def worker_context(**kwargs):
    return request_context(RequestContext(channel="websocket", chat_id="worker", session_key="websocket:worker", turn_id="turn-1", **kwargs))


async def test_progress_is_passive_and_available_in_coordinator_context(setup):
    _, manager, bus = setup
    tool = ReportWorkTool(manager, bus)
    with worker_context():
        result = json.loads(await tool.execute(state="progress", summary="One check passed"))
    assert result["delivery_status"] == "recorded" and bus.inbound_size == 0
    provider = CreateSessionTool(manager)
    block = await provider._provide_runtime_context(RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))
    assert "One check passed" in block.content
    assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]["status"] == "active"
    await manager.state.discard("websocket:worker")
    assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report"]["summary"] == "One check passed"


async def test_question_wakes_without_blocking_and_unchanged_question_does_not_repeat(setup):
    _, manager, bus = setup
    tool = ReportWorkTool(manager, bus)
    with worker_context():
        first = json.loads(await tool.execute(state="progress", summary="Working", human_action="Which dataset?"))
        assert first["delivery_status"] == "queued"
        message = await bus.consume_inbound()
        assert message.session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" and not message.is_user_input
        assert message.metadata["_work_report"]["human_action"] == "Which dataset?"
        second = json.loads(await tool.execute(state="progress", summary="Another check passed"))
        assert second["delivery_status"] == "recorded" and bus.inbound_size == 0
        metadata = (await manager.state.read_metadata("websocket:worker"))["metadata"]
        assert metadata["work_report"]["human_action"] == "Which dataset?"
        assert metadata["goal_state"]["status"] == "active"
        await tool.execute(state="progress", summary="Question resolved", human_action="")
    assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report"]["human_action"] is None


async def test_ready_retains_artifacts_but_only_goal_tool_finishes_goal(setup):
    _, manager, bus = setup
    tool = ReportWorkTool(manager, bus)
    with worker_context():
        report = json.loads(await tool.execute(state="ready", summary="Verified", artifacts=["/tmp/result.txt"]))
        assert report["delivery_status"] == "queued"
        metadata = (await manager.state.read_metadata("websocket:worker"))["metadata"]
        assert metadata["goal_state"]["status"] == "active"
        await UpdateGoalTool(manager).execute(action="complete", recap="Verified")
    incoming = await bus.consume_inbound()
    assert incoming.metadata["_work_report"]["artifacts"] == ["/tmp/result.txt"]
    registry = ToolRegistry()
    registry.register(SendSessionMessageTool(sessions=manager, bus=bus))
    loop = SimpleNamespace(sessions=manager, tools=registry, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0)
    await wake_due_goals(loop)
    assert bus.inbound_size == 0  # Completion reuses the already queued ready report.
    assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]["report_delivered"]


async def test_reviewable_result_can_carry_a_decision_question_without_completing_goal(setup):
    _, manager, bus = setup
    with worker_context():
        tool = ReportWorkTool(manager, bus)
        result = await tool.execute(state="ready", summary="Two validated options are ready",
                                    artifacts=["/tmp/comparison.md"], human_action="Which option should proceed?")
        assert json.loads(result)["delivery_status"] == "queued"
        incoming = await bus.consume_inbound()
        assert incoming.metadata["_work_report"]["state"] == "ready"
        assert incoming.metadata["_work_report"]["human_action"] == "Which option should proceed?"
        await tool.execute(state="ready", summary="Additional verification complete")
        current = (await manager.state.read_metadata("websocket:worker"))["metadata"]
        assert current["work_report"]["human_action"] == "Which option should proceed?"
        assert current["goal_state"]["status"] == "active"
        await tool.execute(state="ready", summary="Owner chose option A", human_action="")
        assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report"]["human_action"] is None


async def test_scheduler_waits_for_running_turn_to_publish_its_detailed_failure(setup):
    from cirno_core.agent.work_reports import record_execution_report
    _, manager, bus = setup
    goal = (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]
    await manager.state.update_metadata("websocket:worker", {"goal_state": {
        **goal, "status": "blocked", "recap": "Execution stopped: error",
    }})
    registry = ToolRegistry()
    registry.register(SendSessionMessageTool(sessions=manager, bus=bus))
    loop = SimpleNamespace(sessions=manager, tools=registry, _pending_queues={"websocket:worker": object()},
                           _discarding_sessions=set(), goal_continuation_limit=0)
    await wake_due_goals(loop)
    assert bus.inbound_size == 0
    assert "work_report" not in (await manager.state.read_metadata("websocket:worker"))["metadata"]
    failure = await record_execution_report(manager, "websocket:worker", turn_id="failed-turn",
                                            stop_reason="error", failure_error_kind="invalid_response")
    loop._pending_queues.clear()
    await wake_due_goals(loop)
    message = await bus.consume_inbound()
    assert message.metadata["_work_report"]["id"] == failure["id"]
    assert message.metadata["_work_report"]["state"] == "failed"
    await wake_due_goals(loop)
    assert bus.inbound_size == 0


async def test_failed_delivery_is_visible_and_retried_with_same_report_id(setup):
    _, manager, bus = setup
    report = await save_work_report(manager, "websocket:worker", state="failed", summary="Provider unavailable")
    sender = SimpleNamespace(enqueue=AsyncMock(side_effect=RuntimeError("inbox unavailable")))
    with pytest.raises(SessionMessageError, match="inbox unavailable"):
        await deliver_work_report(manager, sender, "websocket:worker", report)
    saved = (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report"]
    assert saved["delivery_status"] == "pending" and saved["error"] == "inbox unavailable"
    saved["retry_at"] = None
    await manager.state.update_metadata("websocket:worker", {"work_report": saved})
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    await deliver_work_report(manager, sender, "websocket:worker", saved)
    incoming = await bus.consume_inbound()
    assert incoming.metadata["_session_message"]["message_id"] == report["id"]


async def test_passive_progress_does_not_discard_an_undelivered_result(setup):
    _, manager, bus = setup
    result = await save_work_report(manager, "websocket:worker", state="ready", summary="Result saved")
    await save_work_report(manager, "websocket:worker", state="progress", summary="Checking another item")
    metadata = (await manager.state.read_metadata("websocket:worker"))["metadata"]
    assert metadata["work_report"]["summary"] == "Checking another item"
    assert [item["id"] for item in metadata["work_report_pending"]] == [result["id"]]
    await deliver_work_report(manager, SendSessionMessageTool(sessions=manager, bus=bus), "websocket:worker", result)
    assert (await bus.consume_inbound()).metadata["_work_report"]["summary"] == "Result saved"
    assert not (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report_pending"]


async def test_deleted_report_source_is_not_recreated(setup):
    _, manager, _ = setup
    await manager.state.delete("websocket:worker")
    with pytest.raises(ValueError, match="no longer exists"):
        await save_work_report(manager, "websocket:worker", state="ready", summary="Late result")
    assert await manager.state.read_header("websocket:worker") is None


async def test_inbox_deduplication_survives_consumption_and_restart(setup):
    home, manager, bus = setup
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    values = dict(source_session_key="websocket:worker", target_handle="Cirno", content="Unique result", expect_reply=False, message_id="report-123")
    await sender.enqueue(**values)
    message = await bus.consume_inbound()
    identifier = message.metadata["_recovery_followup_id"]
    await manager.state.acknowledge_followups("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", [identifier])
    restored = SessionManager(home / "workspace", sessions_root=home / "sessions")
    try:
        sender = SendSessionMessageTool(sessions=restored, bus=bus)
        await sender.enqueue(**values)
        assert bus.inbound_size == 0
        with pytest.raises(SessionConflictError, match="different content"):
            await sender.enqueue(**{**values, "content": "Changed payload"})
        assert not pending_followups(await restored.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))
    finally:
        await restored.state.aclose()


async def test_delegation_preserves_original_request_and_reference(setup):
    _, manager, _ = setup
    with request_context(RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", original_user_text="Keep every original measurement; compare both datasets.", turn_id="original-turn", message_id="original-message")):
        result = json.loads(await CreateSessionTool(manager).execute(title="Compare datasets", objective="Compare the datasets"))
    metadata = (await manager.state.read_metadata(result["session_key"]))["metadata"]
    assert metadata["delegation_source"] == {
        "session_key": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "turn_id": "original-turn", "message_id": "original-message",
        "text": "Keep every original measurement; compare both datasets.", "truncated": False,
    }
    block = await CreateSessionTool(manager)._provide_runtime_context(RequestContext(channel="websocket", chat_id="worker", session_key=result["session_key"]))
    assert "Keep every original measurement" in block.content


async def test_cirno_and_ptc_share_worker_tools_but_only_cirno_can_message_user(setup):
    from cirno_core.agent.tools.filesystem import ReadFileTool, WriteFileTool
    from cirno_core.agent.tools.message import MessageTool
    _, manager, bus = setup
    registry = ToolRegistry()
    for tool in (ReadFileTool(), WriteFileTool(), MessageTool(), ReportWorkTool(manager, bus), SetSessionTitleTool(manager, bus)):
        registry.register(tool)
    router = conversation_tools(registry, "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")
    regular = conversation_tools(registry, "websocket:worker")
    assert router.has("user__message") and router.has("files__read")
    assert router.has("conversations__set_title")
    assert regular.has("conversations__set_title")
    assert router.has("files__write") and router.has("conversations__report")
    assert regular.has("files__write") and regular.has("conversations__report") and not regular.has("user__message")
    ptc = conversation_tools(registry, "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", ptc_mode=True)
    assert '"name":"files.write"' in ptc.model_instructions()
    assert '"name":"conversations.set_title"' in ptc.model_instructions()
    with request_context(RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")):
        result = await ReportWorkTool(manager, bus).execute(state="ready", summary="Wrong role")
    assert result.is_error


async def test_live_and_late_duplicate_messages_run_once(setup):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    home, manager, bus = setup
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    await sender.enqueue(source_session_key="websocket:worker", target_handle="Cirno", content="One report", expect_reply=False, message_id="live-duplicate")
    message = await bus.consume_inbound()
    entered, release = asyncio.Event(), asyncio.Event()
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    async def respond(**kwargs):
        entered.set()
        await release.wait()
        return LLMResponse(content="Internal status recorded")
    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model", session_manager=manager)
    try:
        await loop.dispatch.enqueue(message)
        await asyncio.wait_for(entered.wait(), 5)
        await loop.dispatch.enqueue(message)
        release.set()
        tasks = [task for group in loop._active_tasks.values() for task in group]
        await asyncio.gather(*tasks)
        await loop.dispatch.enqueue(message)
        assert provider.chat_stream_with_retry.await_count == 1
        assert not pending_followups(await manager.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))
    finally:
        release.set()
        await loop.aclose()


async def test_old_pending_journal_id_is_consumed_without_replay(setup):
    _, manager, bus = setup
    envelope = {"message_id": "legacy-id", "created_at_ms": 1, "expect_reply": False,
                "source_handle": "bomo", "source_session_key": "websocket:worker", "target_session_key": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"}
    legacy = {"pending_user_followups": [{
        "id": "old-random-journal-id", "sender_id": "session", "channel": "system", "input_role": "user",
        "chat_id": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "content": "Old pending input", "metadata": {"_session_message": envelope},
    }]}
    manager._store.update_metadata("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", legacy)  # Seed a pre-receipt release.
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    values = dict(source_session_key="websocket:worker", target_handle="Cirno", content="Old pending input", expect_reply=False, message_id="legacy-id")
    await sender.enqueue(**values)
    message = await bus.consume_inbound()
    assert message.metadata["_recovery_followup_id"] == "old-random-journal-id"
    assert len(pending_followups(await manager.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))) == 1
    await manager.state.acknowledge_followups("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", ["old-random-journal-id"])
    await sender.enqueue(**values)
    assert bus.inbound_size == 0
    assert not pending_followups(await manager.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))


async def test_replaced_source_cannot_publish_an_old_execution_report(setup):
    _, manager, bus = setup
    old = await manager.state.get_header("websocket:worker")
    await manager.state.reset("websocket:worker")
    with worker_context(session_generation=old.generation):
        result = await ReportWorkTool(manager, bus).execute(state="ready", summary="Obsolete result")
    assert result.is_error and "replaced" in result
    assert bus.inbound_size == 0


async def test_report_retries_while_worker_is_busy(setup):
    _, manager, bus = setup
    await save_work_report(manager, "websocket:worker", state="blocked", summary="Needs credentials")
    registry = ToolRegistry()
    registry.register(SendSessionMessageTool(sessions=manager, bus=bus))
    loop = SimpleNamespace(sessions=manager, tools=registry, _pending_queues={"websocket:worker": object()}, _discarding_sessions=set(), goal_continuation_limit=0)
    await wake_due_goals(loop)
    message = await bus.consume_inbound()
    assert message.metadata["_work_report"]["state"] == "blocked"


async def test_full_worker_report_to_cirno_user_message_pipeline(setup):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.turn_delivery import TurnDeliveryFactory
    from cirno_core.bus.events import InboundMessage
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    from cirno_core.providers.tool_calls import ToolCallRequest
    from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy

    home, manager, bus = setup
    await manager.state.update_metadata("websocket:worker", {"goal_state": None})
    artifact = home / "workspace" / "verified.txt"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text("Verified artifact", encoding="utf-8")
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    counts = {"worker": 0, "cirno": 0}
    async def respond(**kwargs):
        coordinator = "# Personal Router Conversation" in kwargs["messages"][0]["content"]
        role = "cirno" if coordinator else "worker"
        counts[role] += 1
        available = {item["function"]["name"] for item in kwargs["tools"]}
        if coordinator:
            assert "shell__exec" in available and "files__write" in available
            assert "user__message" in available and "conversations__report" in available
            assert "Verified with one check" in str(kwargs["messages"])
            if counts[role] == 1:
                return LLMResponse(content=None, tool_calls=[ToolCallRequest(id="visible-result", name="user__message", arguments={"content": "Result verified; see the attachment.", "media": [str(artifact)]})])
        else:
            assert "user__message" not in available and "conversations__report" in available
            if counts[role] == 1:
                return LLMResponse(content=None, tool_calls=[ToolCallRequest(id="work-report", name="conversations__report", arguments={"state": "ready", "summary": "Verified with one check", "artifacts": [str(artifact)]})])
        return LLMResponse(content="Internal coordination complete" if coordinator else "Worker result ready")
    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model", session_manager=manager)
    loop.turn_delivery_factory = TurnDeliveryFactory(bus, route_policy=WebuiTurnRoutePolicy(manager))
    try:
        await loop.dispatch.enqueue(InboundMessage(channel="websocket", chat_id="worker", sender_id="user", content="Run the bounded verification", require_existing_session=True))
        await asyncio.wait_for(asyncio.gather(*[task for group in loop._active_tasks.values() for task in group]), 10)
        assert bus.inbound_size == 1
        message = await bus.consume_inbound()
        assert not message.is_user_input
        await loop.dispatch.enqueue(message)
        await asyncio.wait_for(asyncio.gather(*[task for group in loop._active_tasks.values() for task in group]), 10)
        visible = []
        while bus.outbound_size:
            output = await bus.consume_outbound()
            if output.chat_id == "b1ec9323-2155-5f24-bc56-1da2f59aeecb" and output.content:
                visible.append(output)
        assert len(visible) == 1 and visible[0].media == [str(artifact)]
        assert counts == {"worker": 2, "cirno": 2}
        assert not pending_followups(await manager.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))
    finally:
        await loop.aclose()


async def test_deleted_goal_during_scheduler_tick_does_not_block_other_goals(setup, monkeypatch):
    _, manager, _ = setup
    await manager.state.update_metadata("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", {"goal_state": {
        "goal_id": "global-work", "status": "active", "objective": "Coordinate work",
    }})
    original = manager.state.mutate_metadata
    deleted = False

    async def delete_before_wake(key, change, **kwargs):
        nonlocal deleted
        if key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" and not deleted:
            deleted = True
            await manager.state.delete(key)
        return await original(key, change, **kwargs)

    monkeypatch.setattr(manager.state, "mutate_metadata", delete_before_wake)
    enqueue = AsyncMock()
    loop = SimpleNamespace(sessions=manager, tools=ToolRegistry(), _pending_queues={},
                           _discarding_sessions=set(), goal_continuation_limit=0, dispatch=SimpleNamespace(enqueue=enqueue))
    await wake_due_goals(loop)
    assert deleted
    assert await manager.state.read_header("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb") is None
    assert enqueue.await_count == 1
    assert enqueue.call_args.args[0].session_key == "websocket:worker"


async def test_delegated_instruction_is_saved_and_marked_with_its_source(setup):
    _, manager, _ = setup
    with request_context(RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")):
        created = json.loads(await CreateSessionTool(manager).execute(title="Read a document", objective="Read the document and verify its claims"))
    session = await manager.state.read(created["session_key"])
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "Read the document and verify its claims"
    facts = await manager.state.project_history(session.key, lambda history: history.all_facts())
    from cirno_core.session.session_handles import SessionHandleResolver
    source = await SessionHandleResolver(manager).ahandle_for_session("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")
    assert facts[0].content["session_message"]["session"] == source.public_payload()


@pytest.mark.parametrize(("reason", "category", "output"), [
    ("completed", None, "Verified final result"),
    ("error", "connection", "LLM connection failed after retries"),
    ("empty_final_response", None, ""),
])
async def test_runtime_reports_results_without_model_reporting_tool(setup, reason, category, output):
    from cirno_core.agent.work_reports import record_execution_report
    _, manager, bus = setup
    await manager.state.update_metadata("websocket:worker", {"goal_state": None})
    report = await record_execution_report(manager, "websocket:worker", turn_id="execution-1", stop_reason=reason,
                                           output=output, failure_error_kind=category, model="failed-model")
    assert report["state"] == ("ready" if reason == "completed" else "failed")
    await deliver_work_report(manager, SendSessionMessageTool(sessions=manager, bus=bus), "websocket:worker", report)
    incoming = await bus.consume_inbound()
    assert incoming.session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" and not incoming.is_user_input
    assert incoming.metadata["_work_report"]["execution"]["failure_error_kind"] == category
    assert incoming.metadata["_work_report"]["execution"]["model"] == "failed-model"
    same = await record_execution_report(manager, "websocket:worker", turn_id="execution-1", stop_reason=reason,
                                         output=output, failure_error_kind=category, model="failed-model")
    await deliver_work_report(manager, SendSessionMessageTool(sessions=manager, bus=bus), "websocket:worker", same)
    assert bus.inbound_size == 0


@pytest.mark.parametrize("initial_status", ["active", "waiting"])
async def test_runtime_failure_blocks_goal_and_scheduler_keeps_detailed_failure(setup, initial_status):
    from cirno_core.agent.work_reports import record_execution_report
    _, manager, bus = setup
    goal = (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]
    await manager.state.update_metadata("websocket:worker", {"goal_state": {**goal, "status": initial_status}})
    report = await record_execution_report(manager, "websocket:worker", turn_id="failed-turn", stop_reason="error",
                                           output="HTTP 401: credential rejected", failure_error_kind="authentication")
    metadata = (await manager.state.read_metadata("websocket:worker"))["metadata"]
    assert metadata["goal_state"]["status"] == "blocked"
    assert "credential rejected" in metadata["goal_state"]["recap"]
    registry = ToolRegistry()
    registry.register(SendSessionMessageTool(sessions=manager, bus=bus))
    loop = SimpleNamespace(sessions=manager, tools=registry, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0)
    await wake_due_goals(loop)
    message = await bus.consume_inbound()
    assert message.metadata["_work_report"]["id"] == report["id"]
    assert message.metadata["_work_report"]["state"] == "failed"
    assert message.metadata["_work_report"]["execution"]["failure_error_kind"] == "authentication"
    await wake_due_goals(loop)
    assert bus.inbound_size == 0


async def test_execution_reporting_respects_goal_segments_and_ordinary_chats(setup):
    from cirno_core.agent.work_reports import record_execution_report
    _, manager, _ = setup
    assert await record_execution_report(manager, "websocket:worker", turn_id="segment", stop_reason="completed", output="Working") is None
    assert await record_execution_report(manager, "websocket:worker", turn_id="segment", stop_reason="max_iterations", continuation_pending=True) is None
    assert await record_execution_report(manager, "websocket:worker", turn_id="stopped", stop_reason="cancelled") is None
    await manager.state.get("websocket:ordinary")
    assert await record_execution_report(manager, "websocket:ordinary", turn_id="ordinary", stop_reason="completed", output="Hello") is None
    assert await record_execution_report(manager, "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", turn_id="cirno", stop_reason="error") is None


@pytest.mark.parametrize("raises", [False, True])
async def test_loop_automatically_delivers_llm_failure_to_cirno(setup, raises):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.bus.events import InboundMessage
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    home, manager, bus = setup
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    provider.chat_stream_with_retry = AsyncMock(
        side_effect=RuntimeError("Provider service unavailable") if raises else None,
        return_value=LLMResponse(content="Provider unavailable after retries", finish_reason="error", error_kind="server_error", error_status_code=503),
    )
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model", session_manager=manager)
    try:
        message = InboundMessage(channel="websocket", chat_id="worker", sender_id="user", content="Continue the delegated research")
        if raises:
            with pytest.raises(RuntimeError, match="Provider service unavailable"):
                await loop.processing.process(message)
        else:
            await loop.processing.process(message)
        assert bus.inbound_size == 1
        incoming = await bus.consume_inbound()
        report = incoming.metadata["_work_report"]
        assert incoming.session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb" and not incoming.is_user_input
        assert report["state"] == "failed" and "unavailable" in report["summary"]
        assert report["execution"]["model"] == "test-model"
        if not raises:
            assert report["execution"]["failure_error_kind"] == "server"
        else:
            assert report["execution"]["stage"] == "run"
        goal = (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]
        assert goal["status"] == "blocked" and goal["objective"] == "Verify a result"
    finally:
        await loop.aclose()


@pytest.mark.parametrize("recovery_event", ["recovered", "cleared"])
async def test_retry_notice_arrives_while_worker_is_running_and_recovers_once(setup, recovery_event):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.bus.agent_events import RetryStatusEvent
    from cirno_core.bus.events import InboundMessage
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    home, manager, bus = setup
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    waiting, proceed = asyncio.Event(), asyncio.Event()

    async def respond(**kwargs):
        events = kwargs["provider_context"].events
        await events.emit(RetryStatusEvent("waiting", 1, None, "timeout", next_retry_at=123))
        await events.emit(RetryStatusEvent("waiting", 2, None, "timeout", next_retry_at=124))
        waiting.set()
        await proceed.wait()
        await events.emit(RetryStatusEvent(recovery_event, 3, None, "unknown"))
        goal = (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]
        await manager.state.update_metadata("websocket:worker", {"goal_state": {**goal, "status": "waiting"}})
        return LLMResponse(content="The service recovered; waiting for an experiment result")

    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model", session_manager=manager)
    task = asyncio.create_task(loop.processing.process(InboundMessage(channel="websocket", chat_id="worker", sender_id="user", content="Continue")))
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        assert not task.done() and bus.inbound_size == 1
        notice = await bus.consume_inbound()
        assert notice.metadata["_work_report"]["state"] == "waiting"
        assert notice.metadata["_work_report"]["execution"]["failure_error_kind"] == "timeout"
        assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]["status"] == "active"
        proceed.set()
        await asyncio.wait_for(task, 5)
        assert bus.inbound_size == 1
        recovery = await bus.consume_inbound()
        assert recovery.metadata["_work_report"]["state"] == "progress"
        assert recovery.metadata["_work_report"]["execution"]["retry_status"] == "recovered"
        assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]["status"] == "waiting"
    finally:
        proceed.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await loop.aclose()


async def test_undelivered_retry_health_coalesces_without_losing_results(setup):
    from cirno_core.agent.work_reports import record_retry_report
    from cirno_core.bus.agent_events import RetryStatusEvent
    _, manager, _ = setup
    result = await save_work_report(manager, "websocket:worker", state="ready", summary="Keep this verified artifact")
    for episode in range(30):
        latest = await record_retry_report(manager, "websocket:worker", turn_id="same-turn", episode=episode,
                                           event=RetryStatusEvent("waiting" if episode % 2 == 0 else "recovered", 1, None, "connection"))
    pending = (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report_pending"]
    assert [report["id"] for report in pending] == [result["id"], latest["id"]]


async def test_terminal_execution_retires_stale_retry_delivery_and_keeps_other_results(setup):
    from cirno_core.agent.work_reports import record_execution_report, record_retry_report
    from cirno_core.bus.agent_events import RetryStatusEvent
    _, manager, bus = setup
    verified = await save_work_report(manager, "websocket:worker", state="ready", summary="Keep this artifact")
    waiting = await record_retry_report(manager, "websocket:worker", turn_id="same-turn", episode=1,
                                       event=RetryStatusEvent("waiting", 1, 4, "connection"))
    failed = await record_execution_report(manager, "websocket:worker", turn_id="same-turn", stop_reason="error", failure_error_kind="connection", output="Retries exhausted")
    metadata = (await manager.state.read_metadata("websocket:worker"))["metadata"]
    assert [item["id"] for item in metadata["work_report_pending"]] == [verified["id"], failed["id"]]
    assert failed["execution_id"] == waiting["execution_id"]
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    assert await deliver_work_report(manager, sender, "websocket:worker", waiting) == "superseded"
    assert bus.inbound_size == 0
    await deliver_work_report(manager, sender, "websocket:worker", failed)
    message = await bus.consume_inbound()
    update = message.metadata["_work_report"]
    assert update["turn_id"] == "same-turn" and update["execution_id"] == waiting["execution_id"]
    assert update["state"] == "failed"
    await manager.state.acknowledge_followups(message.session_key, [message.metadata["_recovery_followup_id"]])
    again = await record_execution_report(manager, "websocket:worker", turn_id="same-turn", stop_reason="error", failure_error_kind="connection", output="Retries exhausted")
    assert again["id"] == failed["id"]
    await save_work_report(manager, "websocket:worker", state="progress", summary="Another result is being inspected")
    again = await record_execution_report(manager, "websocket:worker", turn_id="same-turn", stop_reason="error", failure_error_kind="connection", output="Retries exhausted")
    assert again["id"] == failed["id"]
    await deliver_work_report(manager, sender, "websocket:worker", again)
    assert bus.inbound_size == 0


async def test_legacy_runtime_delivery_keeps_its_receipt_payload_after_upgrade(setup):
    from cirno_core.agent.work_reports import record_execution_report
    _, manager, bus = setup
    legacy = await record_execution_report(manager, "websocket:worker", turn_id="old-turn", stop_reason="error", output="Old failure")
    legacy.pop("execution_id")
    legacy["id"] = "legacy-runtime-report"
    await manager.state.update_metadata("websocket:worker", {"work_report": legacy, "work_report_pending": [legacy]})
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    await deliver_work_report(manager, sender, "websocket:worker", legacy)
    message = await bus.consume_inbound()
    old_payload = message.metadata["_work_report"]
    assert "execution_id" not in old_payload and "turn_id" not in old_payload
    await manager.state.acknowledge_followups(message.session_key, [message.metadata["_recovery_followup_id"]])
    # Crash after accepted delivery but before settling the source receipt.
    await manager.state.update_metadata("websocket:worker", {"work_report": legacy, "work_report_pending": [legacy]})
    await deliver_work_report(manager, sender, "websocket:worker", legacy)
    assert bus.inbound_size == 0


async def test_long_goal_recap_does_not_block_other_goals(setup):
    _, manager, _ = setup
    await manager.state.get("websocket:another")
    await manager.state.update_metadata("websocket:another", {"goal_state": {"goal_id": "another", "status": "active", "objective": "Continue independent work"}})
    await manager.state.update_metadata("websocket:worker", {"goal_state": {"goal_id": "done", "status": "completed", "objective": "Research", "recap": "R" * 8000, "report_to": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"}})
    enqueue = AsyncMock()
    loop = SimpleNamespace(sessions=manager, tools=None, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0, dispatch=SimpleNamespace(enqueue=enqueue))
    await wake_due_goals(loop)
    enqueue.assert_awaited_once()
    assert enqueue.call_args.args[0].session_key == "websocket:another"
    report = (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report"]
    assert len(report["summary"]) <= 4000 and "excerpt" in report["summary"]


async def test_full_report_queue_drains_and_does_not_block_other_goals(setup):
    _, manager, bus = setup
    for index in range(20):
        await save_work_report(manager, "websocket:worker", state="ready", summary=f"Result {index}")
    await manager.state.get("websocket:another")
    await manager.state.update_metadata("websocket:another", {"goal_state": {"goal_id": "another", "status": "active", "objective": "Independent work"}})
    await manager.state.update_metadata("websocket:worker", {"goal_state": {"goal_id": "new-done", "status": "completed", "objective": "New result", "report_to": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"}})
    registry = ToolRegistry()
    registry.register(SendSessionMessageTool(sessions=manager, bus=bus, max_outgoing_messages_per_minute=100))
    enqueue = AsyncMock()
    loop = SimpleNamespace(sessions=manager, tools=registry, _pending_queues={}, _discarding_sessions=set(), goal_continuation_limit=0, dispatch=SimpleNamespace(enqueue=enqueue))
    await wake_due_goals(loop)
    enqueue.assert_awaited_once()
    metadata = (await manager.state.read_metadata("websocket:worker"))["metadata"]
    assert not metadata["work_report_pending"]
    assert not metadata["goal_state"].get("report_delivered")
    assert bus.inbound_size == 20
    await wake_due_goals(loop)
    assert bus.inbound_size == 21
    messages = [await bus.consume_inbound() for _ in range(21)]
    assert messages[-1].metadata["_work_report"]["goal_id"] == "new-done"
    assert (await manager.state.read_metadata("websocket:worker"))["metadata"]["goal_state"]["report_delivered"]


async def test_inbox_failure_preserves_success_and_retries_without_rerunning_work(setup, monkeypatch):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.bus.events import InboundMessage
    from cirno_core.notifications.inbox import NotificationInbox
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    home, manager, bus = setup
    await manager.state.update_metadata("websocket:worker", {"goal_state": {}})
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content="Verified result"))
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model", session_manager=manager)
    record = NotificationInbox.record
    monkeypatch.setattr(NotificationInbox, "record", MagicMock(side_effect=OSError("Inbox disk unavailable")))
    try:
        response = await loop.processing.process(InboundMessage(channel="websocket", chat_id="worker", sender_id="user", content="Finish research"))
        assert response is not None and response.content == "Verified result"
        header = await manager.state.read_metadata("websocket:worker")
        report = header["metadata"]["work_report"]
        assert report["state"] == "ready" and report["delivery_status"] == "queued"
        assert report["notification_pending"] and "unavailable" in report["notification_error"]
        assert (await bus.consume_inbound()).metadata["_work_report"]["state"] == "ready"
        pending = header["metadata"]["work_report_pending"]
        pending[0]["notification_retry_at"] = None
        await manager.state.update_metadata("websocket:worker", {"work_report_pending": pending})
        monkeypatch.setattr(NotificationInbox, "record", record)
        await wake_due_goals(loop)
        assert NotificationInbox().get("report:" + report["id"])["status"] == "ready"
        assert not (await manager.state.read_metadata("websocket:worker"))["metadata"]["work_report_pending"]
        provider.chat_stream_with_retry.assert_awaited_once()
        assert bus.inbound_size == 0
    finally:
        await loop.aclose()


async def test_old_work_report_cannot_be_delivered_as_replaced_conversation(setup):
    _, manager, bus = setup
    key = "websocket:worker"
    report = await save_work_report(manager, key, state="failed", summary="Old execution failed")
    await manager.state.reset(key)
    with pytest.raises(SessionConflictError):
        await deliver_work_report(manager, SendSessionMessageTool(sessions=manager, bus=bus), key, report)
    assert bus.inbound_size == 0
    assert "work_report_pending" not in (await manager.state.read_header(key)).metadata


async def test_report_delivery_acknowledgement_cannot_modify_replacement_context(setup):
    _, manager, _ = setup
    key = "websocket:worker"
    report = await save_work_report(manager, key, state="ready", summary="Old result")

    async def replace_while_delivering(**kwargs):
        await manager.state.reset(key)
        await manager.state.update_metadata(key, {"title": "New task"})

    sender = SimpleNamespace(enqueue=AsyncMock(side_effect=replace_while_delivering))
    with pytest.raises(SessionConflictError):
        await deliver_work_report(manager, sender, key, report)
    metadata = (await manager.state.read_header(key)).metadata
    assert metadata["title"] == "New task"
    assert "work_report_pending" not in metadata
