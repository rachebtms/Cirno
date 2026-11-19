"""Accepted cross-conversation sends settle notification and reply ownership."""

import asyncio
from types import SimpleNamespace

import pytest
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.session_messages import SendSessionMessageTool
from cirno_core.bus.queue import MessageBus
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_handles import SessionHandleResolver


@pytest.fixture
async def sending(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    source = await sessions.state.get_header("websocket:source")
    await sessions.state.get_header("websocket:target")
    target = await SessionHandleResolver(sessions).ahandle_for_session("websocket:target")
    bus = MessageBus()
    timers = []

    def schedule(seconds, callback):
        timer = SimpleNamespace(cancel=lambda: None, seconds=seconds, callback=callback)
        timers.append(timer)
        return timer

    tool = SendSessionMessageTool(sessions=sessions, bus=bus, schedule_later=schedule)
    context = RequestContext(
        channel="websocket",
        chat_id="source",
        session_key=source.key,
        session_generation=source.generation,
        turn_id="fixture-turn",
    )
    try:
        yield sessions, bus, tool, timers, context, target
    finally:
        for pending in tool._pending_replies.values():
            pending.timer.cancel()
        await sessions.state.aclose()


@pytest.mark.parametrize("expect_reply", [False, True])
async def test_stop_after_message_commit_finishes_send_receipt(sending, monkeypatch, expect_reply):
    sessions, bus, tool, timers, context, target = sending
    entered, release = asyncio.Event(), asyncio.Event()
    queue = sessions.state.queue_followup

    async def committed_then_blocked(*args, **kwargs):
        result = await queue(*args, **kwargs)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(sessions.state, "queue_followup", committed_then_blocked)
    with request_context(context):
        task = asyncio.create_task(
            tool.execute(
                to=target.id,
                content="fixture request",
                expect_reply=expect_reply,
                reply_timeout_seconds=5 if expect_reply else None,
            )
        )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done(), "Stop returned before the accepted message send settled"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert bus.inbound.qsize() == 1
        assert len(tool._sent_at[context.session_key]) == 1
        assert len(timers) == int(expect_reply)
        assert len(tool._pending_replies) == int(expect_reply)
        metadata = (await sessions.state.read_metadata(target.session_key))["metadata"]
        assert len(metadata["pending_user_followups"]) == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
