"""Coordination contracts: passive facts, explicit attention and durable inbox receipts."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno.agent.goals.scheduler import wake_due_goals
from cirno.agent.tools.context import RequestContext, request_context
from cirno.agent.tools.coordination import CreateSessionTool, ReportWorkTool, SetSessionTitleTool
from cirno.agent.tools.long_task import UpdateGoalTool
from cirno.agent.tools.registry import ToolRegistry
from cirno.agent.tools.selection import conversation_tools
from cirno.agent.tools.session_messages import SendSessionMessageTool, SessionMessageError
from cirno.agent.work_reports import deliver_work_report, save_work_report
from cirno.bus.queue import MessageBus
from cirno.config.home import set_home_path
from cirno.session.manager import SessionManager
from cirno.session.recovery import pending_followups
from cirno.session.sqlite_store import SessionConflictError


@pytest.fixture
async def setup(tmp_path):
    home = tmp_path / "home"
    set_home_path(home)
    manager = SessionManager(home / "workspace", sessions_root=home / "sessions")
    for key in ("websocket:global", "websocket:worker"):
        await manager.state.get(key)
    await manager.state.update_metadata("websocket:worker", {
        "delegated_by": "websocket:global",
        "goal_state": {"goal_id": "task-1", "objective": "Verify a result", "status": "active", "report_to": "websocket:global"},
    })
    bus = MessageBus()
    yield home, manager, bus
    await manager.state.aclose()
    set_home_path(None)


def worker_context(**kwargs):
    return request_context(RequestContext(channel="websocket", chat_id="worker", session_key="websocket:worker", turn_id="turn-1", **kwargs))


async def test_progress_is_passive_and_available_in_coordinator_context(setup):
    _, manager, bus = setup
    tool = ReportWorkTool(manager, bus)
    with worker_context():
        result = json.loads(await tool.execute(state="progress", summary="One check passed"))
    assert result["delivery_status"] == "recorded" and bus.inbound_size == 0
    provider = CreateSessionTool(manager)
    block = await provider._provide_runtime_context(RequestContext(channel="websocket", chat_id="global", session_key="websocket:global"))
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
        assert message.session_key == "websocket:global" and not message.is_user_input
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
    await manager.state.acknowledge_followups("websocket:global", [identifier])
    restored = SessionManager(home / "workspace", sessions_root=home / "sessions")
    try:
        sender = SendSessionMessageTool(sessions=restored, bus=bus)
        await sender.enqueue(**values)
        assert bus.inbound_size == 0
        with pytest.raises(SessionConflictError, match="different content"):
            await sender.enqueue(**{**values, "content": "Changed payload"})
        assert not pending_followups(await restored.state.read("websocket:global"))
    finally:
        await restored.state.aclose()


async def test_delegation_preserves_original_request_and_reference(setup):
    _, manager, _ = setup
    with request_context(RequestContext(channel="websocket", chat_id="global", session_key="websocket:global", original_user_text="Keep every original measurement; compare both datasets.", turn_id="original-turn", message_id="original-message")):
        result = json.loads(await CreateSessionTool(manager).execute(title="Compare datasets", objective="Compare the datasets"))
    metadata = (await manager.state.read_metadata(result["session_key"]))["metadata"]
    assert metadata["delegation_source"] == {
        "session_key": "websocket:global", "turn_id": "original-turn", "message_id": "original-message",
        "text": "Keep every original measurement; compare both datasets.", "truncated": False,
    }
    block = await CreateSessionTool(manager)._provide_runtime_context(RequestContext(channel="websocket", chat_id="worker", session_key=result["session_key"]))
    assert "Keep every original measurement" in block.content


async def test_router_and_ptc_cannot_execute_worker_tools(setup):
    from cirno.agent.tools.filesystem import ReadFileTool, WriteFileTool
    from cirno.agent.tools.message import MessageTool
    _, manager, bus = setup
    registry = ToolRegistry()
    for tool in (ReadFileTool(), WriteFileTool(), MessageTool(), ReportWorkTool(manager, bus), SetSessionTitleTool(manager, bus)):
        registry.register(tool)
    router = conversation_tools(registry, "websocket:global")
    regular = conversation_tools(registry, "websocket:worker")
    assert router.has("user__message") and router.has("files__read")
    assert not router.has("conversations__set_title")
    assert regular.has("conversations__set_title")
    assert not router.has("files__write") and not router.has("conversations__report")
    assert regular.has("files__write") and regular.has("conversations__report") and not regular.has("user__message")
    ptc = conversation_tools(registry, "websocket:global", ptc_mode=True)
    assert "tools.files.write(" not in ptc.sdk_prompt()
    assert "tools.conversations.set_title(" not in ptc.sdk_prompt()
    with request_context(RequestContext(channel="websocket", chat_id="global", session_key="websocket:global")):
        result = await ReportWorkTool(manager, bus).execute(state="ready", summary="Wrong role")
    assert result.is_error


async def test_live_and_late_duplicate_messages_run_once(setup):
    from cirno.agent.loop import AgentLoop
    from cirno.providers.base import GenerationSettings, LLMResponse
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
        await loop._enqueue_session_message(message)
        await asyncio.wait_for(entered.wait(), 5)
        await loop._enqueue_session_message(message)
        release.set()
        tasks = [task for group in loop._active_tasks.values() for task in group]
        await asyncio.gather(*tasks)
        await loop._enqueue_session_message(message)
        assert provider.chat_stream_with_retry.await_count == 1
        assert not pending_followups(await manager.state.read("websocket:global"))
    finally:
        release.set()
        await loop.aclose()


async def test_old_pending_journal_id_is_consumed_without_replay(setup):
    _, manager, bus = setup
    envelope = {"message_id": "legacy-id", "created_at_ms": 1, "expect_reply": False,
                "source_handle": "bomo", "source_session_key": "websocket:worker", "target_session_key": "websocket:global"}
    legacy = {"pending_user_followups": [{
        "id": "old-random-journal-id", "sender_id": "session", "channel": "system", "input_role": "user",
        "chat_id": "websocket:global", "content": "Old pending input", "metadata": {"_session_message": envelope},
    }]}
    manager._store.update_metadata("websocket:global", legacy)  # Seed a pre-receipt release.
    sender = SendSessionMessageTool(sessions=manager, bus=bus)
    values = dict(source_session_key="websocket:worker", target_handle="Cirno", content="Old pending input", expect_reply=False, message_id="legacy-id")
    await sender.enqueue(**values)
    message = await bus.consume_inbound()
    assert message.metadata["_recovery_followup_id"] == "old-random-journal-id"
    assert len(pending_followups(await manager.state.read("websocket:global"))) == 1
    await manager.state.acknowledge_followups("websocket:global", ["old-random-journal-id"])
    await sender.enqueue(**values)
    assert bus.inbound_size == 0
    assert not pending_followups(await manager.state.read("websocket:global"))


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
    from cirno.agent.loop import AgentLoop
    from cirno.agent.turn_delivery import TurnDeliveryFactory
    from cirno.bus.events import InboundMessage
    from cirno.providers.base import GenerationSettings, LLMResponse, ToolCallRequest
    from cirno.session.webui_turns import WebuiTurnRoutePolicy

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
        coordinator = "# Cirno Conversation" in kwargs["messages"][0]["content"]
        role = "cirno" if coordinator else "worker"
        counts[role] += 1
        available = {item["function"]["name"] for item in kwargs["tools"]}
        if coordinator:
            assert "shell__exec" not in available and "files__write" not in available
            assert "user__message" in available and "conversations__report" not in available
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
        await loop._enqueue_session_message(InboundMessage(channel="websocket", chat_id="worker", sender_id="user", content="Run the bounded verification", require_existing_session=True))
        await asyncio.wait_for(asyncio.gather(*[task for group in loop._active_tasks.values() for task in group]), 10)
        assert bus.inbound_size == 1
        message = await bus.consume_inbound()
        assert not message.is_user_input
        await loop._enqueue_session_message(message)
        await asyncio.wait_for(asyncio.gather(*[task for group in loop._active_tasks.values() for task in group]), 10)
        visible = []
        while bus.outbound_size:
            output = await bus.consume_outbound()
            if output.chat_id == "global" and output.content:
                visible.append(output)
        assert len(visible) == 1 and visible[0].media == [str(artifact)]
        assert counts == {"worker": 2, "cirno": 2}
        assert not pending_followups(await manager.state.read("websocket:global"))
    finally:
        await loop.aclose()


async def test_deleted_goal_during_scheduler_tick_does_not_block_other_goals(setup, monkeypatch):
    _, manager, _ = setup
    await manager.state.update_metadata("websocket:global", {"goal_state": {
        "goal_id": "global-work", "status": "active", "objective": "Coordinate work",
    }})
    original = manager.state.mutate_metadata
    deleted = False

    async def delete_before_wake(key, change, **kwargs):
        nonlocal deleted
        if key == "websocket:global" and not deleted:
            deleted = True
            await manager.state.delete(key)
        return await original(key, change, **kwargs)

    monkeypatch.setattr(manager.state, "mutate_metadata", delete_before_wake)
    enqueue = AsyncMock()
    loop = SimpleNamespace(sessions=manager, tools=ToolRegistry(), _pending_queues={},
                           _discarding_sessions=set(), goal_continuation_limit=0, _enqueue_session_message=enqueue)
    await wake_due_goals(loop)
    assert deleted
    assert await manager.state.read_header("websocket:global") is None
    assert enqueue.await_count == 1
    assert enqueue.call_args.args[0].session_key == "websocket:worker"


async def test_delegated_instruction_is_saved_and_marked_with_its_source(setup):
    _, manager, _ = setup
    with request_context(RequestContext(channel="websocket", chat_id="global", session_key="websocket:global")):
        created = json.loads(await CreateSessionTool(manager).execute(title="Read a document", objective="Read the document and verify its claims"))
    session = await manager.state.read(created["session_key"])
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "Read the document and verify its claims"
    facts = await manager.state.project_history(session.key, lambda history: history.all_facts())
    from cirno.session.session_handles import SessionHandleResolver
    source = await SessionHandleResolver(manager).ahandle_for_session("websocket:global")
    assert facts[0].content["session_message"]["session"] == source.public_payload()
