"""Real Dream leases survive failed, cancelled and unconfirmed executions."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.command.builtin.dream import cmd_dream
from cirno_core.command.router import CommandContext
from cirno_core.memory.dream_run import run_dream
from cirno_memory.repository import MemoryRepository


@pytest.fixture
async def agent(tmp_path):
    agent = AgentLoop(
        bus=MessageBus(),
        provider=MagicMock(aclose=AsyncMock()),
        workspace=tmp_path,
        model="test-model",
        context_window_tokens=128_000,
    )
    agent.context.memory.journal.append_history("Measured sample A: 43.2 at 280 K.")
    try:
        yield agent
    finally:
        await agent.aclose()


def pending_batch(agent):
    with MemoryRepository(agent.context.memory.workspace).connect() as db:
        return dict(db.execute("SELECT * FROM dream_queue").fetchone())


@pytest.mark.parametrize("stage", ["prepare", "model"])
async def test_failed_dream_releases_batch_and_preserves_cursor(agent, stage):
    failure = RuntimeError(f"{stage} unavailable")
    prepare = AsyncMock(side_effect=failure if stage == "prepare" else None)
    agent.process_direct = AsyncMock(side_effect=failure)

    with pytest.raises(RuntimeError, match=f"{stage} unavailable"):
        await run_dream(agent, commit_subject="dream: test", prepare=prepare)

    assert agent.context.memory.journal.get_last_dream_cursor() == 0
    row = pending_batch(agent)
    assert row["lease"] is None
    assert row["error"] == str(failure)
    assert row["retry_after"] > 0
    if stage == "prepare":
        agent.process_direct.assert_not_called()


async def test_completed_dream_does_not_ack_unconfirmed_input(agent):
    agent.process_direct = AsyncMock(
        return_value=OutboundMessage(
            channel="cli",
            chat_id="dream",
            content="done",
            metadata={"_stop_reason": "completed"},
        )
    )

    result = await run_dream(agent, commit_subject="dream: test")

    assert result.status == "incomplete"
    assert result.reason == "1 inputs remain unconfirmed or failed"
    assert agent.context.memory.journal.get_last_dream_cursor() == 0
    row = pending_batch(agent)
    assert row["lease"] is None
    assert row["retry_after"] > 0


async def test_manual_dream_reports_failure_and_keeps_it_on_the_owned_task(agent):
    agent.process_direct = AsyncMock(side_effect=RuntimeError("model unavailable"))
    message = InboundMessage(channel="cli", sender_id="owner", chat_id="dream", content="/dream")
    await cmd_dream(
        CommandContext(
            msg=message,
            session=None,
            key=message.session_key,
            raw="/dream",
            loop=agent,
        )
    )
    task = next(iter(agent._background_tasks))

    with pytest.raises(RuntimeError, match="model unavailable"):
        await task
    await asyncio.sleep(0)

    assert not agent._background_tasks
    assert agent.bus.outbound_size == 1
    failure = agent.bus.outbound.get_nowait()
    assert failure.content == "Dream failed: model unavailable"
    assert (failure.channel, failure.chat_id) == ("cli", "dream")
    assert agent.context.memory.journal.get_last_dream_cursor() == 0
    assert pending_batch(agent)["lease"] is None


async def test_manual_dream_is_tracked_and_cancellation_requeues_without_penalty(agent):
    started = asyncio.Event()

    async def wait_for_cancel(*_args, **_kwargs):
        started.set()
        await asyncio.Event().wait()

    agent.process_direct = wait_for_cancel
    message = InboundMessage(channel="cli", sender_id="owner", chat_id="dream", content="/dream")
    response = await cmd_dream(
        CommandContext(
            msg=message,
            session=None,
            key=message.session_key,
            raw="/dream",
            loop=agent,
        )
    )
    assert response.content == "Dreaming..."
    await asyncio.wait_for(started.wait(), timeout=3)
    assert agent.lifecycle.has_pending_work()
    assert len(agent._background_tasks) == 1
    task = next(iter(agent._background_tasks))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert not agent._background_tasks
    assert agent.context.memory.journal.get_last_dream_cursor() == 0
    row = pending_batch(agent)
    assert row["lease"] is None
    assert row["attempts"] == 0
    assert row["retry_after"] == 0
    assert agent.bus.outbound_size == 0


async def test_prompt_preparation_failure_releases_the_claimed_batch(agent, monkeypatch):
    def unavailable_template():
        raise OSError("Dream prompt unavailable")

    monkeypatch.setattr(agent.context.memory.dream, "_template", unavailable_template)
    with pytest.raises(OSError, match="prompt unavailable"):
        await run_dream(agent, commit_subject="dream: failed preparation")
    row = pending_batch(agent)
    assert row["lease"] is None
    assert row["error"] == "Dream prompt unavailable"
    assert agent.context.memory.journal.get_last_dream_cursor() == 0


async def test_preparation_yields_and_cancellation_settles_its_physical_worker(agent, monkeypatch):
    from threading import Event, Timer

    started, release, finished = Event(), Event(), Event()
    original = agent.context.memory.dream.build_prompt

    def prepare():
        started.set()
        release.wait()
        try:
            return original()
        finally:
            finished.set()

    monkeypatch.setattr(agent.context.memory.dream, "build_prompt", prepare)
    agent.process_direct = AsyncMock(return_value=OutboundMessage(
        channel="cli", chat_id="dream", content="done", metadata={"_stop_reason": "completed"},
    ))
    emergency_release = Timer(2, release.set)
    emergency_release.start()
    task = asyncio.create_task(run_dream(agent, commit_subject="dream: preparation cancellation"))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(started.wait), 3)
        assert not finished.is_set(), "Dream preparation blocked foreground dispatch"
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Cancellation released a still-running batch worker"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        row = pending_batch(agent)
        assert finished.is_set() and row["lease"] is None
        assert row["attempts"] == 0 and row["retry_after"] == 0
        agent.process_direct.assert_not_awaited()
    finally:
        release.set()
        emergency_release.cancel()
        await asyncio.to_thread(emergency_release.join)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
