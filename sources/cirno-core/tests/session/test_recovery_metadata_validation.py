"""Malformed retained recovery data must not abort the owning startup scan."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import (
    PENDING_USER_TURN_KEY,
    RECOVERY_METADATA_KEY,
    RUNTIME_CHECKPOINT_KEY,
)
from cirno_core.session.recovery.restart import RecoveryRestart
from cirno_core.session.recovery.state import recovery_state_from_metadata, resume_message_count


@pytest.mark.parametrize("bad_state", [
    {"status": [], "recovery_id": "broken"},
    {"status": {}, "recovery_id": "broken"},
    {"status": "resuming", "recovery_id": ""},
])
async def test_scan_ignores_unusable_recovery_headers_and_reaches_other_pending_conversations(tmp_path, bad_state):
    sessions = SessionManager(tmp_path)
    delivery = SimpleNamespace(publish=AsyncMock(), requeue_pending_followups=AsyncMock())
    try:
        broken = await sessions.state.import_messages("websocket:broken", [{"role": "user", "content": "Earlier input"}])
        await sessions.state.update_metadata(broken.key, {RECOVERY_METADATA_KEY: bad_state})
        pending = await sessions.state.import_messages("websocket:pending", [{"role": "user", "content": "Retain this pending task"}])
        pending.metadata[PENDING_USER_TURN_KEY] = True
        await sessions.state.prepare_input(pending)
        restart = RecoveryRestart(sessions, delivery)
        # Explicit ordering proves that one malformed header cannot hide the next session.
        with patch.object(RecoveryRestart, "_recovery_candidates", AsyncMock(return_value=[broken.key, pending.key])):
            await restart.scan()
        calls = delivery.publish.call_args_list
        assert len(calls) == 1
        assert calls[0].args[0] == "pending"
        assert calls[0].args[1]["status"] == "awaiting_user"
        assert calls[0].args[1]["reason"] == "restart_requires_confirmation"
        assert (await sessions.state.get(broken.key)).metadata[RECOVERY_METADATA_KEY] == bad_state
        assert (await sessions.state.get(pending.key)).messages[0]["content"] == "Retain this pending task"
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("value", [True, False])
def test_boolean_metadata_is_not_a_retry_attempt_or_resume_boundary(value):
    metadata = {RECOVERY_METADATA_KEY: {"status": "resuming", "recovery_id": "valid", "attempts": value,
                                       "resume_message_count": value}}
    state = recovery_state_from_metadata(metadata)
    assert state == {"status": "resuming", "recovery_id": "valid"}
    assert resume_message_count(Session(key="websocket:resume", metadata=metadata)) is None


@pytest.mark.parametrize("phase", [[], {}])
async def test_nontext_checkpoint_phase_uses_review_only_unknown_checkpoint_path(tmp_path, phase):
    sessions = SessionManager(tmp_path)
    delivery = SimpleNamespace(publish=AsyncMock(), requeue_pending_followups=AsyncMock())
    try:
        session = await sessions.state.get("websocket:unknown-phase")
        session.add_message("user", "Keep the task context")
        session.metadata.update({PENDING_USER_TURN_KEY: True, RUNTIME_CHECKPOINT_KEY: {"phase": phase}})
        await sessions.state.prepare_input(session)
        await RecoveryRestart(sessions, delivery).scan()
        saved = await sessions.state.get(session.key)
        state = saved.metadata[RECOVERY_METADATA_KEY]
        assert state["status"] == "awaiting_user"
        assert state["reason"] == "checkpoint_unknown"
        assert state["can_continue"] is False
        assert RUNTIME_CHECKPOINT_KEY not in saved.metadata
        assert PENDING_USER_TURN_KEY not in saved.metadata
        assert saved.messages[0]["content"] == "Keep the task context"
        assert saved.messages[-1]["_recovery_interrupted"] is True
    finally:
        await sessions.state.aclose()
