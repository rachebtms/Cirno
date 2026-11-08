import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.session_messages import SendSessionMessageTool
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.outbound_events import UserInputEvent
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import UserInputAccepted
from cirno_core.providers.contracts import LLMResponse
from cirno_core.runtime.context import public_history_message
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_core.session.session_messages import SESSION_MESSAGE_METADATA_KEY
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
from cirno_core.session.presentation_history import record_from_fact


@pytest.fixture
async def loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path / "state")
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = SimpleNamespace(max_tokens=4096)
    provider.chat_stream_with_retry = AsyncMock(
        return_value=LLMResponse(content="Reviewed", tool_calls=[], usage=None)
    )
    agent = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )
    try:
        yield agent
    finally:
        await agent.aclose()


def _message(content: str = "Please review") -> InboundMessage:
    envelope = {
        "message_id": "message-1",
        "created_at_ms": 1,
        "expect_reply": True,
        "source_handle": "luma",
        "source_session_key": "websocket:source",
        "target_session_key": "telegram:target",
    }
    return InboundMessage(
        channel="system",
        sender_id="session",
        chat_id="telegram:target",
        content=content,
        metadata={SESSION_MESSAGE_METADATA_KEY: envelope},
        session_key_override="telegram:target",
        input_role="user",
    )


@pytest.mark.asyncio
async def test_session_message_runs_as_user_input_and_replies_on_target_route(
    loop: AgentLoop,
) -> None:
    loop.sessions.save(loop.sessions.get_or_create("telegram:target"))
    msg = _message()

    response = await loop.processing.process(msg)

    assert response is not None
    assert (response.channel, response.chat_id, response.content) == (
        "telegram",
        "target",
        "Reviewed",
    )
    provider_messages = loop.provider.chat_stream_with_retry.await_args.kwargs["messages"]
    provider_input = next(
        row for row in reversed(provider_messages) if row.get("role") == "user"
    )
    assert provider_input["content"].startswith("Please review")
    assert "Message from @luma." in provider_input["content"]
    assert "Reply with send_session_message." in provider_input["content"]

    stored = loop.sessions.get_or_create("telegram:target").messages
    user_row = next(row for row in stored if row.get("role") == "user")
    assert public_history_message(user_row)["content"] == "Please review"
    assert SESSION_MESSAGE_METADATA_KEY not in user_row


@pytest.mark.asyncio
async def test_session_message_text_is_not_dispatched_as_a_slash_command(
    loop: AgentLoop,
) -> None:
    loop.sessions.save(loop.sessions.get_or_create("telegram:target"))
    await loop.dispatch.receive(_message("/stop"))
    await asyncio.wait_for(
        asyncio.gather(*loop._active_tasks["telegram:target"]), timeout=2,
    )
    response = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=2)

    assert response.content == "Reviewed"
    loop.provider.chat_stream_with_retry.assert_awaited_once()


async def test_path_followup_reaches_running_turn(loop: AgentLoop) -> None:
    first_call = asyncio.Event()
    release = asyncio.Event()
    calls = []
    path = "/home/user/project"

    async def respond(**kwargs):
        calls.append(str(kwargs["messages"]))
        if len(calls) == 1:
            first_call.set()
            await release.wait()
        return LLMResponse(content="Reviewed")

    loop.provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    run = asyncio.create_task(loop.run())
    try:
        await loop.bus.publish_inbound(InboundMessage(
            channel="weixin", sender_id="user", chat_id="path", content="Review the project",
        ))
        await asyncio.wait_for(first_call.wait(), 3)
        await loop.bus.publish_inbound(InboundMessage(
            channel="weixin", sender_id="user", chat_id="path", content=path,
        ))
        async with asyncio.timeout(3):
            while loop._pending_queues["weixin:path"].empty():
                await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(asyncio.gather(*loop._active_tasks["weixin:path"]), 5)

        assert len(calls) == 2
        assert path in calls[1]
        session = loop.sessions.get_or_create("weixin:path")
        visible = [public_history_message(row) for row in session.messages]
        assert any(row["content"] == path for row in visible)
        assert not any(row.get("_command") for row in session.messages)
    finally:
        release.set()
        loop.stop()
        await asyncio.wait_for(run, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize("message_count", [1, 2], ids=["idle", "active"])
async def test_cross_session_input_preserves_source_in_live_events_and_history(
    loop: AgentLoop, message_count: int,
) -> None:
    source_key, target_key = "websocket:source", "websocket:target"
    await loop.sessions.state.get(source_key)
    await loop.sessions.state.get(target_key)
    await loop.sessions.state.mutate_metadata(target_key, lambda metadata: metadata.update(webui=True))
    handles = SessionHandleResolver(loop.sessions)
    source = await handles.ahandle_for_session(source_key)
    destination = await handles.ahandle_for_session(target_key)
    assert source is not None and destination is not None
    tool = SendSessionMessageTool(sessions=loop.sessions, bus=loop.bus)
    coordinator = WebuiTurnCoordinator(
        bus=loop.bus, sessions=loop.sessions,
        schedule_background=lambda coro: coro.close(),
    )
    disconnect = coordinator.subscribe()
    accepted = []
    disconnect_accepted = loop.bus.subscribe(accepted.append, UserInputAccepted)
    loop.bus.publish_outbound = AsyncMock()
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(**kwargs):
        started.set()
        await release.wait()
        return LLMResponse(content="Reviewed", tool_calls=[], usage=None)

    loop.provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    run = asyncio.create_task(loop.run())
    try:
        for index in range(message_count):
            with request_context(RequestContext(
                channel="websocket", chat_id="source", session_key=source_key,
            )):
                result = await tool.execute(
                    to=destination.name, content=f"Review {index}", expect_reply=False,
                )
            assert result == f"Queued to @{destination.name}."
            async with asyncio.timeout(3):
                while len(accepted) < index + 1:
                    await asyncio.sleep(0)
            await asyncio.wait_for(started.wait(), 3)
        release.set()
        await asyncio.wait_for(
            asyncio.gather(*loop._active_tasks[target_key]), 5,
        )
        assert len(accepted) == message_count
        events = [
            call.args[0].event for call in loop.bus.publish_outbound.await_args_list
            if isinstance(call.args[0].event, UserInputEvent)
        ]
        assert [event.content for event in events] == [f"Review {i}" for i in range(message_count)]
        provenance = {"id": source.id, "name": source.name}
        assert all(event.provenance["session_message"]["session"] == provenance for event in events)
        # Reconnect/reload must preserve provenance, not just live events.
        records = await loop.sessions.state.project_history(
            target_key,
            lambda history: [record_from_fact(fact, target_key) for fact in history.all_facts()],
        )
        inputs = [record for record in records if record.get("event") == "user"]
        assert [record["text"] for record in inputs] == [f"Review {i}" for i in range(message_count)]
        assert all(record["session_message"]["session"] == provenance for record in inputs)
        loop.provider.chat_stream_with_retry.assert_awaited()
    finally:
        release.set()
        disconnect()
        disconnect_accepted()
        run.cancel()
        await asyncio.gather(run, return_exceptions=True)


@pytest.mark.parametrize("content", ["/stop", "Late request"])
async def test_replaced_session_rejects_delayed_input_before_commands_or_notifications(loop, monkeypatch, content):
    key = "websocket:replaced"
    old = await loop.sessions.state.get(key)
    await loop.sessions.state.reset(key)
    accepted = AsyncMock()
    priority = AsyncMock()
    enqueue = AsyncMock()
    monkeypatch.setattr(loop.runtime_event_publisher, "user_input_accepted", accepted)
    monkeypatch.setattr(loop.command_execution, "dispatch_inline", priority)
    monkeypatch.setattr(loop.dispatch, "enqueue", enqueue)
    await loop.dispatch.receive(InboundMessage(
        channel="websocket", sender_id="user", chat_id="replaced", content=content,
        require_existing_session=True, session_generation=old.generation,
    ))
    accepted.assert_not_awaited()
    priority.assert_not_awaited()
    enqueue.assert_not_awaited()


async def test_duplicate_coordination_input_has_one_visible_prompt_and_one_execution(loop, monkeypatch):
    key = "websocket:deduplicated"
    await loop.sessions.state.get("websocket:source")
    await loop.sessions.state.get(key)
    await loop.sessions.state.update_metadata(key, {"webui": True})
    handles = SessionHandleResolver(loop.sessions)
    target = await handles.ahandle_for_session(key)
    sender = SendSessionMessageTool(sessions=loop.sessions, bus=loop.bus)
    await sender.enqueue(source_session_key="websocket:source", target_handle=target.name,
                         content="Inspect once", expect_reply=False, message_id="duplicate-display")
    message = await loop.bus.consume_inbound()
    coordinator = WebuiTurnCoordinator(loop.bus, loop.sessions, loop.schedule_background)
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(**kwargs):
        entered.set()
        await release.wait()
        return LLMResponse(content="Done")

    monkeypatch.setattr(loop.provider, "chat_stream_with_retry", AsyncMock(side_effect=respond))
    try:
        with coordinator.connected():
            await loop.dispatch.receive(message)
            await asyncio.wait_for(entered.wait(), 3)
            await loop.dispatch.receive(message)
            release.set()
            await asyncio.wait_for(asyncio.gather(*loop._active_tasks[key]), 3)
            await loop.dispatch.receive(message)
        rows = await loop.sessions.state.project_history(key, lambda reader: [
            record_from_fact(fact, key) for fact in reader.all_facts()
        ])
        assert [row["text"] for row in rows if row["event"] == "user"] == ["Inspect once"]
        loop.provider.chat_stream_with_retry.assert_awaited_once()
    finally:
        release.set()


async def test_coordination_display_write_is_bound_to_accepted_generation(loop, monkeypatch):
    from cirno_core.session.webui_turns import coordinator as turns_coordinator
    from cirno_core.bus.runtime_events import RuntimeEventContext

    key = "websocket:display-race"
    original_session = await loop.sessions.state.get(key)
    await loop.sessions.state.update_metadata(key, {"webui": True})
    append = turns_coordinator.append_session_message_input

    async def replace_before_append(*args, **kwargs):
        await loop.sessions.state.reset(key)
        await append(*args, **kwargs)

    monkeypatch.setattr(turns_coordinator, "append_session_message_input", replace_before_append)
    coordinator = WebuiTurnCoordinator(loop.bus, loop.sessions, loop.schedule_background)
    with coordinator.connected():
        await loop.bus.publish(UserInputAccepted(
            context=RuntimeEventContext(channel="system", chat_id=key, session_key=key,
                session_generation=original_session.generation,
                metadata={SESSION_MESSAGE_METADATA_KEY: {
                    "message_id": "late-display", "created_at_ms": 1, "expect_reply": False,
                    "source_handle": "cirno", "source_session_key": "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "target_session_key": key,
                }}),
            content="Message accepted before clearing",
        ))
    assert await loop.sessions.state.project_history(key, lambda reader: list(reader.all_facts())) == []
    assert not any(isinstance(message.event, UserInputEvent) for message in loop.bus.outbound._queue)
