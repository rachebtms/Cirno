"""A fresh consolidation can cover history before an unpersisted continuation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.execution.checkpoints import RuntimeCheckpointWriter
from cirno_core.agent.execution.persistence import TurnPersistence
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.checkpoints import restore_runtime_checkpoint
from cirno_core.session.recovery.contracts import RUNTIME_CHECKPOINT_KEY
from cirno_core.session.summary import SessionSummaryCheckpoint, summary_context_message
from cirno_core.session.turn_continuation import save_skip_for_turn


@pytest.mark.parametrize("mode,archived", [
    ("continuation", 6100), ("replayed-input", 0), ("persisted-input", 0),
    ("fresh-input", 0), ("no-new-input", 0),
])
async def test_startup_consolidation_maps_the_history_boundary(tmp_path, mode, archived):
    sessions = SessionManager(tmp_path)
    session = await sessions.state.get("websocket:long-research")
    for index in range(archived):
        session.add_message("user" if index % 2 == 0 else "assistant", f"Archived research {index}")
    session.commit_summary_checkpoint("Earlier research summary")
    session.add_message("user", "Continue the unfinished measurements")
    session.add_message("assistant", "Measurement r95 completed")
    history = session.get_history()
    current = None if mode == "no-new-input" else "Continue from saved progress"
    persisted_early = mode == "persisted-input"
    if persisted_early:
        session.add_message("user", current)
    await sessions.state.prepare_input(session)
    original = deepcopy(session.messages)
    transcript_input = TranscriptInput(history=history, current_message=current,
                                       session_summary=session.metadata["_last_summary"])
    raw = [{"role": "system", "content": "Fixed policy"},
           summary_context_message("Earlier research summary"), *history]
    if current is not None:
        raw.append({"role": "user", "content": current})
    metadata = {"_internal_continuation": True} if mode == "continuation" else (
        {"_skip_user_persist": True} if mode == "replayed-input" else {}
    )
    start = transcript_input.message_count if current is None else save_skip_for_turn(
        message_metadata=metadata, initial_message_count=transcript_input.message_count,
        input_persisted_early=persisted_early)
    boundary = transcript_input.message_count - (current is not None)
    writer = RuntimeCheckpointWriter(TurnPersistence(SimpleNamespace(sessions=sessions)), session,
                                     start=start, history_boundary=boundary,
                                     input_persisted_early=persisted_early)
    checkpoint = SessionSummaryCheckpoint("Updated task checkpoint", boundary)
    raw.append({"role": "assistant", "content": "Continue with r96"})
    payload = {"phase": "awaiting_model", "assistant_message": raw[-1], "completed_tool_results": [],
               "pending_tool_calls": [], "_transcript": raw, "_summary_checkpoint": checkpoint}
    try:
        await writer(payload)
        await writer(payload)  # Repeating the same boundary does not insert it twice.
        assert session.metadata["_last_summary"]["text"] == checkpoint.summary
        expected_tail = [current] if mode in {"persisted-input", "fresh-input"} else []
        assert [row["content"] for row in session.get_history()] == [*expected_tail, "Continue with r96"]
        assert session.messages[:len(original) - int(persisted_early)] == original[:len(original) - int(persisted_early)]
        reopened = SessionManager(tmp_path)
        try:
            restored = await reopened.state.get(session.key)
            assert restore_runtime_checkpoint(restored)
            assert not restore_runtime_checkpoint(restored)
            assert restored.get_history() == session.get_history()
            assert restored.metadata["_last_summary"] == session.metadata["_last_summary"]
            # The next automatic turn may consolidate immediately again after
            # restart. It must use its own boundary, without resetting history.
            next_raw = [raw[0], summary_context_message(checkpoint.summary),
                        *restored.get_history(), {"role": "user", "content": "Resume"}]
            next_boundary = len(next_raw) - 1
            resumed = RuntimeCheckpointWriter(TurnPersistence(SimpleNamespace(sessions=reopened)), restored,
                start=len(next_raw), history_boundary=next_boundary, input_persisted_early=False)
            next_raw.append({"role": "assistant", "content": "Next measurement finished"})
            await resumed({**payload, "_transcript": next_raw, "assistant_message": next_raw[-1],
                           "_summary_checkpoint": SessionSummaryCheckpoint("Resumed task", next_boundary)})
            assert [row["content"] for row in restored.get_history()] == ["Next measurement finished"]
            assert restored.metadata["_last_summary"]["text"] == "Resumed task"
            assert raw[0] == {"role": "system", "content": "Fixed policy"}
        finally:
            await reopened.state.aclose()
    finally:
        await sessions.state.aclose()


async def test_invalid_checkpoint_boundary_leaves_session_unchanged(tmp_path):
    sessions = SessionManager(tmp_path)
    session = await sessions.state.get("websocket:invalid-boundary")
    session.add_message("user", "Original task")
    before = deepcopy(session.messages), deepcopy(session.metadata)
    persistence = TurnPersistence(SimpleNamespace(sessions=sessions))
    try:
        with pytest.raises(ValueError, match="Checkpoint summary"):
            await persistence.checkpoint(session, {"phase": "awaiting_model"},
                messages=[{"role": "assistant", "content": "New work"}], skip=0,
                summary_checkpoint=SessionSummaryCheckpoint("Invalid", 99), message_positions={0: 1})
        assert (session.messages, session.metadata) == before
        assert RUNTIME_CHECKPOINT_KEY not in session.metadata
    finally:
        await sessions.state.aclose()
