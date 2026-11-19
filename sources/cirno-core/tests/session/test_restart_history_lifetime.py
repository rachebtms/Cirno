"""Startup recovery never resurrects old history or aborts unrelated sessions."""

from unittest.mock import AsyncMock

import pytest

from cirno_core.bus.queue import MessageBus
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import PENDING_USER_TURN_KEY, RECOVERY_METADATA_KEY
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.recovery.restart import RecoveryRestart


@pytest.mark.parametrize("boundary", ["lookup", "recovery_commit", "failure_commit"])
async def test_restart_scan_retains_replacement_history_and_continues(tmp_path, monkeypatch, boundary):
    sessions = SessionManager(tmp_path)
    coordinator = RecoveryCoordinator(sessions, MessageBus())
    keys = ["websocket:discarded", "websocket:retained"]
    for key in keys:
        draft = await sessions.state.get(key)
        draft.messages.append({"role": "user", "content": "Finish existing work"})
        draft.metadata[PENDING_USER_TURN_KEY] = True
        await sessions.state.restore_interruption(draft)
    monkeypatch.setattr(RecoveryRestart, "_recovery_candidates", AsyncMock(return_value=keys))

    if boundary == "lookup":
        # Both the former creating read and the replacement non-creating read
        # observe deletion at the same boundary after candidate classification.
        for method in ("get", "read"):
            original = getattr(sessions.state, method)

            async def deleted_before_load(key, _original=original):
                if key == keys[0]:
                    await sessions.state.delete(key)
                return await _original(key)

            monkeypatch.setattr(sessions.state, method, deleted_before_load)
    else:
        recover = RecoveryRestart.recover

        async def replaced_before_commit(self, session, chat_id):
            if session.key == keys[0]:
                await sessions.state.reset(session.key)
                if boundary == "failure_commit":
                    raise RuntimeError("Old recovery failed after replacement")
            await recover(self, session, chat_id)

        monkeypatch.setattr(RecoveryRestart, "recover", replaced_before_commit)
    try:
        await coordinator.scan()
        discarded = await sessions.state.read_header(keys[0])
        if boundary == "lookup":
            assert discarded is None
        else:
            assert RECOVERY_METADATA_KEY not in discarded.metadata
            assert not discarded.metadata.get(PENDING_USER_TURN_KEY)
        retained = await sessions.state.read_header(keys[1])
        assert retained.metadata[RECOVERY_METADATA_KEY]["status"] == "awaiting_user"
    finally:
        await sessions.state.aclose()
