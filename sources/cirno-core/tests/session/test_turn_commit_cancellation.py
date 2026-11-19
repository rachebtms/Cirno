"""Accepted writes and their owner-draft acknowledgement settle together."""

import asyncio
import threading
from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import PENDING_USER_TURN_KEY, RUNTIME_CHECKPOINT_KEY


async def test_acknowledgement_is_part_of_the_admitted_session_operation(tmp_path, monkeypatch):
    state = SessionManager(tmp_path).state
    entered, release = asyncio.Event(), asyncio.Event()
    receipts = []

    async def run(_operation, *, write):
        assert write
        entered.set()
        await release.wait()
        return "committed"

    monkeypatch.setattr(state.operations, "run", run)
    task = asyncio.create_task(state.operations.execute(
        "chat:ack", lambda: None, acknowledge=receipts.append,
    ))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert receipts == []
        assert state.operations._admitted == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await state.aclose()
    assert task.cancelled()
    assert receipts == ["committed"]
    assert state.operations._admitted == 0


async def test_failed_operation_never_publishes_an_acknowledgement(tmp_path, monkeypatch):
    state = SessionManager(tmp_path).state
    acknowledge = Mock()
    monkeypatch.setattr(state.operations, "run", AsyncMock(side_effect=OSError("write failed")))
    try:
        with pytest.raises(OSError, match="write failed"):
            await state.operations.execute("chat:ack", lambda: None, acknowledge=acknowledge)
        acknowledge.assert_not_called()
        assert state.operations._admitted == 0
    finally:
        await state.aclose()


async def test_acknowledgement_failure_releases_the_key_before_the_next_operation(tmp_path, monkeypatch):
    state = SessionManager(tmp_path).state
    events = []

    async def run(operation, *, write):
        return operation()

    def commit():
        events.append("committed")
        return "receipt"

    def acknowledge(receipt):
        assert receipt == "receipt"
        events.append("acknowledgement failed")
        raise OSError("cannot acknowledge")

    monkeypatch.setattr(state.operations, "run", run)
    try:
        failed = asyncio.create_task(state.operations.execute("chat:ack", commit, acknowledge=acknowledge))
        following = asyncio.create_task(state.operations.execute("chat:ack", lambda: events.append("following")))
        outcomes = await asyncio.gather(failed, following, return_exceptions=True)
        assert isinstance(outcomes[0], OSError)
        assert outcomes[1] is None
        assert events == ["committed", "acknowledgement failed", "following"]
        assert state.operations._admitted == 0
        assert state.operations._key_tails == {}
    finally:
        await state.aclose()


async def cancel_admitted_write(operation, store, method, monkeypatch):
    original = getattr(store, method)
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def gated(*args, **kwargs):
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(timeout=3):
            raise TimeoutError("test writer was not released")
        return original(*args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(store, method, gated)
        task = asyncio.create_task(operation())
        try:
            await asyncio.wait_for(entered.wait(), timeout=1)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("operation", ["prepare_input", "finish_turn", "restore_interruption"])
async def test_cancelled_commit_refreshes_its_draft_before_an_idempotent_retry(tmp_path, monkeypatch, operation):
    manager = SessionManager(tmp_path)
    state = manager.state
    try:
        draft = await state.get("websocket:acknowledgement")
        draft.add_message("user", "Research request")
        draft.metadata[PENDING_USER_TURN_KEY] = True
        if operation != "prepare_input":
            await state.prepare_input(draft)
            draft.add_message("assistant", "Unique saved response")
        submitted_messages = list(draft.messages)
        commit = getattr(state, operation)
        await cancel_admitted_write(lambda: commit(draft), manager._store, "save", monkeypatch)
        committed = await state.get(draft.key)
        assert committed.messages == submitted_messages
        acknowledged_revision = draft.revision
        acknowledged_persistence = draft.persisted
        await commit(draft)
        await state.discard(draft.key)
        assert (await state.get(draft.key)).messages == submitted_messages
        assert acknowledged_revision == committed.revision
        assert acknowledged_persistence is True
    finally:
        await state.aclose()


async def test_cancelled_checkpoint_acknowledgement_allows_finalization_to_clear_recovery(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    state = manager.state
    try:
        draft = await state.get("websocket:checkpoint-ack")
        draft.add_message("user", "Continue this task")
        draft.metadata[PENDING_USER_TURN_KEY] = True
        await state.prepare_input(draft)
        payload = {"phase": "awaiting_model", "assistant_message": {
            "role": "assistant", "content": "Saved intermediate progress",
        }, "completed_tool_results": [], "pending_tool_calls": []}
        # This matches TurnPersistence.checkpoint's write-before-checkpoint_view contract.
        draft.metadata[RUNTIME_CHECKPOINT_KEY] = payload
        await cancel_admitted_write(lambda: state.checkpoint_view(draft, payload), manager._store,
                                    "save_runtime_checkpoint", monkeypatch)
        assert (await state.get(draft.key)).metadata[RUNTIME_CHECKPOINT_KEY] == payload
        draft.add_message("assistant", "Task completed")
        await state.finish_turn(draft)
        await state.discard(draft.key)
        final = await state.get(draft.key)
        assert RUNTIME_CHECKPOINT_KEY not in final.metadata
        assert PENDING_USER_TURN_KEY not in final.metadata
        assert [message["content"] for message in final.messages] == ["Continue this task", "Task completed"]
    finally:
        await state.aclose()


@pytest.mark.parametrize("checkpoint", [False, True])
async def test_failed_physical_write_does_not_acknowledge_a_new_baseline(tmp_path, monkeypatch, checkpoint):
    manager = SessionManager(tmp_path)
    state = manager.state
    try:
        draft = await state.get("websocket:failed-ack")
        draft.add_message("user", "Keep the original input")
        draft.metadata[PENDING_USER_TURN_KEY] = True
        if checkpoint:
            await state.prepare_input(draft)
        baseline = deepcopy(draft._baseline)
        before = await state.get(draft.key)
        method = "save_runtime_checkpoint" if checkpoint else "save"
        monkeypatch.setattr(manager._store, method, Mock(side_effect=OSError("disk full")))
        with pytest.raises(OSError, match="disk full"):
            if checkpoint:
                await state.checkpoint_view(draft, {"phase": "awaiting_model"})
            else:
                await state.prepare_input(draft)
        assert draft._baseline == baseline
        current = await state.get(draft.key)
        assert current.messages == before.messages
        assert current.metadata == before.metadata
        assert current.revision == before.revision
    finally:
        await state.aclose()
