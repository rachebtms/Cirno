"""Optional accounting must not strand a durably saved consolidation."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.bus.agent_events import ContextCompactionEvent, EventSink
from cirno_core.memory.consolidation import Consolidator
from cirno_core.session.manager import SessionManager
from cirno_core.session.outbound_wire import encode_context_compaction


@pytest.fixture
async def context(tmp_path):
    manager = SessionManager(tmp_path)
    session = await manager.state.import_messages("websocket:postcommit", [
        {"role": "user", "content": "Retain this research objective"},
        {"role": "assistant", "content": "Verified result"},
    ])
    consolidator = Consolidator(
        SimpleNamespace(workspace=tmp_path), manager, Mock(return_value=[]), Mock(return_value=[]),
    )
    consolidator.archive_session = AsyncMock(return_value="Saved task checkpoint")
    consolidator.estimate_session_prompt_tokens = Mock(return_value=(123, "fixture"))
    consolidator.on_compaction_saved = AsyncMock()
    events = []

    async def observe(event):
        if isinstance(event, ContextCompactionEvent):
            events.append(event)

    try:
        yield consolidator, session.key, SimpleNamespace(context_window_tokens=2048), events, EventSink(observe)
    finally:
        await manager.state.aclose()


async def assert_checkpoint(consolidator, key):
    await consolidator.sessions.state.discard(key)
    saved = await consolidator.sessions.state.get(key)
    assert saved.last_archived == 2
    assert saved.metadata["_last_summary"]["text"] == "Saved task checkpoint"
    assert saved.messages[0]["content"] == "Retain this research objective"


@pytest.mark.parametrize("error", [ValueError("invalid fixed memory file"), OSError("cannot read profile")])
async def test_estimation_failure_keeps_success_and_runs_archive_cleanup(context, error):
    consolidator, key, runtime, events, sink = context
    consolidator.estimate_session_prompt_tokens.side_effect = error
    result = await consolidator.compact_idle_session(key, runtime=runtime, events=sink, notify=True)
    assert result == "Saved task checkpoint"
    await assert_checkpoint(consolidator, key)
    assert [event.phase for event in events] == ["started", "succeeded"]
    assert events[0].compaction_id == events[1].compaction_id
    assert events[1].context_tokens is None
    assert events[1].context_estimated is None
    wire = encode_context_compaction("postcommit", events[1])
    assert wire["phase"] == "succeeded"
    assert "context_tokens" not in wire
    assert "context_estimated" not in wire
    consolidator.on_compaction_saved.assert_awaited_once_with(key)


async def test_success_still_reports_measured_context(context):
    consolidator, key, runtime, events, sink = context
    await consolidator.compact_idle_session(key, runtime=runtime, events=sink)
    assert [event.phase for event in events] == ["started", "succeeded"]
    assert events[1].context_tokens == 123
    assert events[1].context_estimated is True
    await assert_checkpoint(consolidator, key)


async def test_postcommit_cancellation_settles_the_completion_event_before_propagating(context):
    consolidator, key, runtime, events, _sink = context
    consolidator.estimate_session_prompt_tokens.side_effect = asyncio.CancelledError()
    publishing = asyncio.Event()
    release = asyncio.Event()

    async def observe(event):
        if event.phase == "succeeded":
            publishing.set()
            await release.wait()
        events.append(event)

    task = asyncio.create_task(consolidator.compact_idle_session(key, runtime=runtime, events=EventSink(observe)))
    waiter = asyncio.create_task(publishing.wait())
    try:
        # A broken implementation exits without publishing completion; do not leave a task alive.
        done, _ = await asyncio.wait({task, waiter}, timeout=1)
        assert publishing.is_set(), f"No completion event; task done={task in done}"
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [event.phase for event in events] == ["started", "succeeded"]
        await assert_checkpoint(consolidator, key)
        consolidator.on_compaction_saved.assert_not_awaited()
    finally:
        release.set()
        task.cancel()
        waiter.cancel()
        await asyncio.gather(task, waiter, return_exceptions=True)


async def test_actual_commit_failure_stays_failed_and_preserves_original_history(context, monkeypatch):
    consolidator, key, runtime, events, sink = context
    monkeypatch.setattr(consolidator.sessions.state, "commit_summary", AsyncMock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        await consolidator.compact_idle_session(key, runtime=runtime, events=sink)
    assert [event.phase for event in events] == ["started", "failed"]
    current = await consolidator.sessions.state.get(key)
    assert current.last_archived == 0
    assert "_last_summary" not in current.metadata
    consolidator.estimate_session_prompt_tokens.assert_not_called()
    consolidator.on_compaction_saved.assert_not_awaited()


async def test_archive_cleanup_failure_is_not_hidden_after_checkpoint_success(context):
    consolidator, key, runtime, events, sink = context
    consolidator.on_compaction_saved.side_effect = OSError("archive disk full")
    with pytest.raises(OSError, match="archive disk full"):
        await consolidator.compact_idle_session(key, runtime=runtime, events=sink)
    assert [event.phase for event in events] == ["started", "succeeded"]
    await assert_checkpoint(consolidator, key)


@pytest.mark.parametrize("write_fails", [False, True])
async def test_cancellation_during_admitted_summary_write_reports_the_actual_commit(
    context, monkeypatch, write_fails,
):
    consolidator, key, runtime, events, sink = context
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    store = consolidator.sessions._store
    save = store.save

    def gated_save(session, **kwargs):
        if session.key == key and "_last_summary" in session.metadata:
            loop.call_soon_threadsafe(entered.set)
            if not release.wait(timeout=3):
                raise TimeoutError("test writer was not released")
            if write_fails:
                raise OSError("summary disk full")
        return save(session, **kwargs)

    monkeypatch.setattr(store, "save", gated_save)
    task = asyncio.create_task(consolidator.compact_idle_session(key, runtime=runtime, events=sink))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert [event.phase for event in events] == ["started"]
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [event.phase for event in events] == ["started", "cancelled" if write_fails else "succeeded"]
        if write_fails:
            saved = await consolidator.sessions.state.get(key)
            assert saved.last_archived == 0
            assert "_last_summary" not in saved.metadata
        else:
            await assert_checkpoint(consolidator, key)
        consolidator.on_compaction_saved.assert_not_awaited()
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
