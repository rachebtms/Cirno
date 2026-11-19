"""Stopping owned work must retain newer progress and replacement histories."""

from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.events import InboundMessage
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY, RECOVERY_METADATA_KEY
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.recovery.pending import pending_followups


@pytest.mark.parametrize("change", ["progress", "completed", "replacement"])
async def test_stop_uses_current_goal_without_mutating_replacement_history(loop_factory, monkeypatch, change):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key = "websocket:stop-history"
    old = await loop.sessions.state.get(key)
    old.messages.append({"role": "user", "content": "Old request"})
    goal = {"goal_id": "old", "objective": "Work", "status": "active", "recap": "Old recap"}
    old.metadata["goal_state"] = goal
    await loop.sessions.state.prepare_input(old)
    await loop.sessions.state.queue_followup(key, InboundMessage(
        "websocket", "owner", "stop-history", "Old followup",
        metadata={PENDING_FOLLOWUP_ID_KEY: "restored"},
    ))
    loop.recovery_admission = RecoveryCoordinator(loop.sessions, loop.bus)
    read = loop.sessions.state.read
    changed = False

    async def updated_after_read(session_key):
        nonlocal changed
        result = await read(session_key)
        if session_key == key and not changed:
            changed = True
            if change == "replacement":
                await loop.sessions.state.reset(key)
                current = await loop.sessions.state.get(key)
                current.messages.append({"role": "user", "content": "New request"})
                current.metadata["goal_state"] = {**goal, "goal_id": "new", "recap": "New work"}
                await loop.sessions.state.prepare_input(current)
                await loop.sessions.state.queue_followup(key, InboundMessage(
                    "websocket", "owner", "stop-history", "New followup",
                    metadata={PENDING_FOLLOWUP_ID_KEY: "restored"},
                ))
            else:
                await loop.sessions.state.update_metadata(key, {"goal_state": {
                    **goal, "status": "completed" if change == "completed" else "active", "recap": "Latest progress",
                }})
        return result

    monkeypatch.setattr(loop.sessions.state, "read", updated_after_read)
    try:
        await loop.cancel_session_work(key)
        current = await read(key)
        if change == "replacement":
            assert current.metadata["goal_state"]["goal_id"] == "new"
            assert current.metadata["goal_state"]["status"] == "active"
            assert RECOVERY_METADATA_KEY not in current.metadata
            assert [row.content for row in pending_followups(current)] == ["New followup"]
        else:
            assert current.metadata["goal_state"]["recap"] == "Latest progress"
            assert current.metadata["goal_state"]["status"] == ("completed" if change == "completed" else "stopped")
    finally:
        await loop.aclose()


@pytest.mark.parametrize("status", ["active", "waiting"])
async def test_stop_scheduled_goal_without_a_worker_retains_continuation(loop_factory, status):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key = "websocket:scheduled-stop"
    draft = await loop.sessions.state.get(key)
    draft.messages.append({"role": "user", "content": "Continue scheduled research"})
    draft.metadata["goal_state"] = {"goal_id": "scheduled", "objective": "Research", "status": status}
    await loop.sessions.state.prepare_input(draft)
    loop.recovery_admission = RecoveryCoordinator(loop.sessions, loop.bus)
    try:
        assert await loop.cancel_session_work(key) == 0
        current = await loop.sessions.state.read_header(key)
        assert current.metadata["goal_state"]["status"] == "stopped"
        assert current.metadata[RECOVERY_METADATA_KEY]["reason"] == "user_stopped"
    finally:
        await loop.aclose()


@pytest.mark.parametrize("has_goal", [False, True])
async def test_stop_idle_completed_conversation_does_not_create_interruption(loop_factory, has_goal):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key = "websocket:idle-history"
    draft = await loop.sessions.state.get(key)
    draft.messages.extend([
        {"role": "user", "content": "Finished request"},
        {"role": "assistant", "content": "All done"},
    ])
    if has_goal:
        draft.metadata["goal_state"] = {"goal_id": "done", "objective": "Done", "status": "completed"}
    await loop.sessions.state.finish_turn(draft)
    loop.recovery_admission = RecoveryCoordinator(loop.sessions, loop.bus)
    try:
        assert await loop.cancel_session_work(key) == 0
        assert RECOVERY_METADATA_KEY not in (await loop.sessions.state.read_header(key)).metadata
    finally:
        await loop.aclose()
