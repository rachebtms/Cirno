"""Stopping a turn owns its durable and visible settlement until it finishes."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.execution.session_turn import SessionTurn
from cirno_core.bus.events import InboundMessage


@pytest.mark.parametrize("policy,stage", [
    *(('stop', stage) for stage in ('abort', 'checkpoint', 'complete', 'idle')),
    *(('shutdown', stage) for stage in ('abort', 'complete', 'idle')),
    *(('discard', stage) for stage in ('abort', 'complete', 'idle')),
    ('finished', 'idle'),
])
async def test_repeated_cancel_drains_checkpoint_completion_and_idle(monkeypatch, policy, stage):
    processing = asyncio.Event()
    settling = asyncio.Event()
    release = asyncio.Event()
    completed = []

    async def settle(name):
        if name == stage:
            settling.set()
            await release.wait()
        completed.append(name)

    async def process(*_args, **_kwargs):
        processing.set()
        if policy == "finished":
            return None
        await asyncio.Future()

    async def abort():
        await settle("abort")

    async def complete(*_args, **_kwargs):
        await settle("complete")

    async def idle():
        await settle("idle")

    async def finish_turn(_session):
        await settle("checkpoint")

    delivery = SimpleNamespace(
        continuation_pending=False,
        abort_stream=AsyncMock(side_effect=abort),
        complete=AsyncMock(side_effect=complete),
        idle=AsyncMock(side_effect=idle),
    )
    monkeypatch.setattr("cirno_core.agent.execution.session_turn.restore_runtime_checkpoint", lambda _session: completed.append("restore"))
    agent = SimpleNamespace(
        dispatch=SimpleNamespace(session_key=lambda _msg: "websocket:cancel-test", failed=AsyncMock()),
        turn_delivery_factory=SimpleNamespace(unrouted=lambda *_args: delivery, create=AsyncMock(return_value=delivery)),
        recovery_admission=None,
        _get_session_lock=lambda _key: asyncio.Lock(),
        _concurrency_gate=None,
        _executing_sessions=set(),
        _discarding_sessions={"websocket:cancel-test"} if policy == "discard" else set(),
        _preserve_inflight_turns_on_shutdown=policy == "shutdown",
        _automation_turn_coordinators=(),
        processing=SimpleNamespace(process=process),
        sessions=SimpleNamespace(state=SimpleNamespace(
            peek_header=lambda *_args, **_kwargs: None,
            get=AsyncMock(return_value=SimpleNamespace()),
            finish_turn=AsyncMock(side_effect=finish_turn),
        )),
    )
    msg = InboundMessage(channel="websocket", sender_id="u", chat_id="cancel-test", content="Task")
    task = asyncio.create_task(SessionTurn(agent).execute(msg, asyncio.Queue()))
    try:
        await asyncio.wait_for(processing.wait(), 1)
        if policy != "finished":
            task.cancel()
        await asyncio.wait_for(settling.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Repeated cancellation abandoned turn settlement"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    expected = (
        ["abort", "restore", "checkpoint", "complete", "idle"] if policy == "stop"
        else ["complete", "idle"] if policy == "finished"
        else ["abort", "complete", "idle"]
    )
    assert completed == expected
    assert not agent._executing_sessions
    agent.dispatch.failed.assert_not_awaited()
