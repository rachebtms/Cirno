"""Editing rewrites context only, with a durable replacement input and new generation."""

import pytest

from cirno_core.bus.events import INBOUND_META_TURN_ID
from cirno_core.session.manager import SessionManager, SessionPolicy
from cirno_core.session.presentation_history import fact_from_record
from cirno_core.session.recovery import pending_followups
from cirno_core.session.sqlite_store import SessionConflictError


@pytest.fixture
async def source(tmp_path):
    sessions = SessionManager(tmp_path / "workspace")
    key = "websocket:edit"
    session = await sessions.state.import_messages(key, [
        {"role": "user", "content": "First question", INBOUND_META_TURN_ID: "first"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "Original question", INBOUND_META_TURN_ID: "second", "media": ["/saved/image.png"]},
        {"role": "assistant", "content": "Later answer"},
    ], metadata={"title": "My conversation", "session_handle": "bomo", "webui": True,
                 "goal_state": {"goal_id": "old-goal", "status": "stopped", "objective": "Old objective"}})
    await sessions.state.set_policy(key, SessionPolicy(log_content=False))
    await sessions.state.append_history(key, [
        fact_from_record({"event": "user", "text": "First question", "turn_id": "first"}),
        fact_from_record({"event": "message", "text": "First answer", "turn_id": "first"}),
        fact_from_record({"event": "user", "text": "Original question", "turn_id": "second"}),
        fact_from_record({"event": "message", "text": "Later answer", "turn_id": "second"}),
    ], expected_generation=session.generation)
    yield sessions, key, session
    await sessions.state.aclose()


async def test_edit_preserves_prefix_policy_attachments_and_external_files(source, tmp_path):
    sessions, key, original = source
    changed_file = tmp_path / "changed-by-agent.txt"
    changed_file.write_text("Side effect remains")
    message = await sessions.state.edit_user_input(key, "second", "Edited question")
    saved = await sessions.state.read(key)
    assert [row["content"] for row in saved.messages] == ["First question", "First answer"]
    assert saved.generation != original.generation
    assert saved.policy.log_content is False
    assert saved.metadata["title"] == "My conversation"
    assert saved.metadata["session_handle"] == "bomo"
    assert "goal_state" not in saved.metadata
    assert message.content == "Edited question"
    assert message.media == ["/saved/image.png"]
    assert message.metadata["_history_generation"] == saved.generation
    assert pending_followups(saved)[0].content == "Edited question"
    assert changed_file.read_text() == "Side effect remains"
    facts = await sessions.state.project_history(key, lambda reader: list(reader.navigation()))
    assert all("Original question" != fact.content.get("text") and "Later answer" != fact.content.get("text") for _, _, fact in facts)
    with pytest.raises(SessionConflictError):
        await sessions.state.update_metadata(key, {"late_write": True}, expected_generation=original.generation)


async def test_edit_rejects_active_stale_system_or_temporary_inputs_without_changes(source):
    sessions, key, original = source
    for values in ({"pending_user_turn": True}, {"runtime_checkpoint": {"phase": "awaiting_tools"}}):
        await sessions.state.mutate_metadata(key, lambda metadata: metadata.update(values))
        with pytest.raises(SessionConflictError, match="Stop"):
            await sessions.state.edit_user_input(key, "second", "New text")
        await sessions.state.mutate_metadata(key, lambda metadata: metadata.pop(next(iter(values))))
    with pytest.raises(ValueError, match="saved human"):
        await sessions.state.edit_user_input(key, "missing", "New text")
    await sessions.state.import_messages(key, [{"role": "user", "content": "System input", INBOUND_META_TURN_ID: "system", "input_origin": {"kind": "heartbeat"}}])
    with pytest.raises(ValueError, match="saved human"):
        await sessions.state.edit_user_input(key, "system", "New text")
    saved = await sessions.state.read(key)
    assert saved.generation == original.generation
    assert any(row["content"] == "Later answer" for row in saved.messages)


async def test_edited_input_is_recoverable_before_bus_delivery(source):
    sessions, key, _ = source
    await sessions.state.edit_user_input(key, "second", "Continue after restart")
    reopened = SessionManager(sessions.workspace, sessions_root=sessions.sessions_dir.parent)
    try:
        saved = await reopened.state.read(key)
        assert [item.content for item in pending_followups(saved)] == ["Continue after restart"]
    finally:
        await reopened.state.aclose()


async def test_authenticated_edit_action_queues_one_real_user_request(source):
    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.instance_api import instance_action
    from cirno_core.bus.input_origin import input_origin
    sessions, key, _ = source
    bus = MessageBus()
    result = await instance_action({"action": "conversations.edit", "values": {
        "session_key": key, "turn_id": "second", "content": "Revised request",
    }}, sessions=sessions, bus=bus)
    assert result["ok"] is True
    message = await bus.consume_inbound()
    assert message.content == "Revised request" and message.is_user_input
    assert message.session_generation == (await sessions.state.read_header(key)).generation
    assert message.metadata[INBOUND_META_TURN_ID] == result["turn_id"]
    assert input_origin(message) is None
    assert bus.inbound_size == 0
