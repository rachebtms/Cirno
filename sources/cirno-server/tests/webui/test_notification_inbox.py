"""Notification history preserves source workflows and remains separate from memory."""

import pytest
from cirno_core.bus.agent_events import ContextCompactionEvent
from cirno_core.bus.events import OutboundMessage
from cirno_core.config.home import set_instance_path
from cirno_core.notifications.inbox import NotificationInbox
from cirno_server.webui.instance_api import instance_action


@pytest.fixture
def inbox(tmp_path):
    set_instance_path(tmp_path)
    yield NotificationInbox(tmp_path / "state")
    set_instance_path(None)


def question(inbox, identifier="a" * 32, session_key="websocket:one"):
    inbox.capture(OutboundMessage(channel="websocket", chat_id=session_key.split(":", 1)[1], content="Which value?", metadata={
        "_agent_ui": {"kind": "user_question", "data": {"id": identifier, "question": "Which value?", "options": ["A", "B"]}},
    }))


def test_question_read_is_not_answer_and_cross_session_quote_cannot_resolve(inbox):
    question(inbox)
    item = inbox.list(category="operations")["items"][0]
    assert item["status"] == "pending" and item["data"]["options"] == ["A", "B"]
    inbox.read(identifiers=[item["id"]])
    assert inbox.list()["items"][0]["status"] == "pending"
    answer = "> [!QUOTE]\n> <!-- cirno-question:" + "a" * 32 + " -->\n> Which value?\n\nA"
    inbox.answer("websocket:other", answer)
    assert inbox.list()["items"][0]["status"] == "pending"
    inbox.answer("websocket:one", answer)
    assert inbox.list()["items"][0]["status"] == "answered"
    assert inbox.list()["unread"]["operations"] == 0


def test_compaction_keeps_error_and_deduplicates_lifecycle(inbox):
    for phase, error in (("started", None), ("failed", "provider connection refused"), ("failed", "provider connection refused")):
        inbox.capture(OutboundMessage(channel="websocket", chat_id="one", content="", event=ContextCompactionEvent("same", phase, error=error)))
    items = inbox.list(category="system")["items"]
    assert len(items) == 1 and items[0]["body"] == "provider connection refused"
    inbox.read(identifiers=[items[0]["id"]])
    inbox.capture(OutboundMessage(channel="websocket", chat_id="one", content="", event=ContextCompactionEvent("same", "succeeded", context_tokens=900)))
    assert inbox.list()["items"][0]["status"] == "succeeded"
    assert inbox.list()["unread"]["system"] == 1


def test_pagination_and_category_read_are_persistent_and_independent(inbox):
    for index in range(6):
        inbox.record(str(index), "system" if index % 2 else "conversations", "message", body=str(index))
    first = inbox.list(limit=2)
    second = NotificationInbox(inbox.path.parent.parent).list(before=first["next_before"], limit=2)
    assert [item["body"] for item in first["items"] + second["items"]] == ["5", "4", "3", "2"]
    inbox.read(category="system")
    assert inbox.list()["unread"] == {"system": 0, "operations": 0, "conversations": 3}
    assert inbox.path.name == "inbox.sqlite3" and inbox.path.parent.name == "notifications"
    assert inbox.path.stat().st_mode & 0o777 == 0o600




async def test_instance_api_reads_and_marks_only_requested_category(inbox):
    inbox.record("sys", "system", "dream")
    inbox.record("msg", "conversations", "message")
    result = await instance_action({"action": "inbox.list", "values": {"category": "system"}}, sessions=None, bus=None)
    assert [item["id"] for item in result["items"]] == ["sys"]
    await instance_action({"action": "inbox.read", "values": {"category": "system"}}, sessions=None, bus=None)
    assert inbox.list()["unread"]["conversations"] == 1
    with pytest.raises(ValueError):
        await instance_action({"action": "inbox.list", "values": {"category": "invalid"}}, sessions=None, bus=None)


async def test_open_notification_does_not_recreate_deleted_or_reset_conversations(inbox, tmp_path):
    from cirno_core.session.manager import SessionManager
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    key = "websocket:source"
    try:
        original = await sessions.state.get_header(key)
        inbox.record("question", "operations", "question", session_key=key, status="pending",
                     data={"session_generation": original.generation})
        payload = {"action": "inbox.open", "values": {"id": "question"}}
        assert (await instance_action(payload, sessions=sessions, bus=None))["session_key"] == key
        await sessions.state.reset(key)
        assert (await instance_action(payload, sessions=sessions, bus=None))["session_key"] is None
        assert inbox.get("question")["status"] == "unavailable"
        await sessions.state.delete(key)
        assert (await instance_action(payload, sessions=sessions, bus=None))["session_key"] is None
        assert await sessions.state.read_header(key) is None
    finally:
        await sessions.state.aclose()


def test_dream_notifications_include_partial_and_failure_results(inbox, monkeypatch):
    from cirno_core.memory.store import MemoryStore
    monkeypatch.setattr("cirno_memory.repository.MemoryRepository.finish", lambda *args, **kwargs: {"retained": 2})
    store = MemoryStore(inbox.path.parent.parent)
    store.dream.finish_batch("batch")
    item = inbox.list()["items"][0]
    assert item["kind"] == "dream" and item["status"] == "partial" and item["data"]["retained"] == 2
    store.dream.finish_batch("other-batch", error="API unavailable")
    assert inbox.list()["items"][0]["body"] == "API unavailable"
    store.dream.finish_batch("preempted", preempted=True)
    assert len(inbox.list()["items"]) == 2


async def test_temporary_questions_never_enter_inbox(inbox, tmp_path):
    from cirno_core.bus.queue import MessageBus
    from cirno_core.config.schema import Config
    from cirno_core.session.manager import SessionManager
    from cirno_server.channels.manager import ChannelManager
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    await sessions.state.register_transient("websocket:temporary-test")
    bus = MessageBus()
    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    manager = ChannelManager(config, bus, session_manager=sessions, config_path=tmp_path / "config.json")
    try:
        await manager.notifications.record(OutboundMessage(channel="websocket", chat_id="temporary-test", content="Private", metadata={
            "_agent_ui": {"kind": "user_question", "data": {"id": "b" * 32, "question": "Private"}},
        }))
        assert not inbox.path.exists()
    finally:
        await manager.stop_all()
        await sessions.state.aclose()


async def test_question_survives_metadata_cache_eviction(inbox, tmp_path):
    from cirno_core.bus.queue import MessageBus
    from cirno_core.config.schema import Config
    from cirno_core.session.manager import SessionManager
    from cirno_server.channels.manager import ChannelManager
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    key = "websocket:renamed"
    original = await sessions.state.get(key)
    await sessions.state.update_metadata(key, {"title": "Renamed"})
    await sessions.state.discard(key)
    assert sessions.state.peek_identity(key) is None
    manager = ChannelManager(Config.model_validate({"channels": {"websocket": {"enabled": False}}}),
                             MessageBus(), session_manager=sessions, config_path=tmp_path / "config.json")
    try:
        await manager.notifications.record(OutboundMessage(channel="websocket", chat_id="renamed", content="Which value?", metadata={
            "_session_key": key, "_session_generation": original.generation,
            "_agent_ui": {"kind": "user_question", "data": {"id": "c" * 32, "question": "Which value?"}},
        }))
        notice = inbox.list()["items"][0]
        assert notice["kind"] == "question" and notice["data"]["session_generation"] == original.generation
        assert notice["data"]["session_title"] == "Renamed"
    finally:
        await manager.stop_all()
        await sessions.state.aclose()


def test_ordinary_replies_and_successful_turns_do_not_enter_inbox(inbox):
    from cirno_core.bus.outbound_events import TurnEndEvent
    for chat_id in ("cirno", "worker"):
        inbox.capture(OutboundMessage(channel="websocket", chat_id=chat_id, content="Hello"))
        inbox.capture(OutboundMessage(channel="websocket", chat_id=chat_id, content="", metadata={"webui_turn_id": "done"},
                                      event=TurnEndEvent(outcome="completed")))
    assert inbox.list()["items"] == []
    inbox.record("report:ready", "conversations", "report", status="ready", body="Task verified")
    assert inbox.list()["items"][0]["body"] == "Task verified"


def test_failed_turns_are_system_events_not_work_reports(inbox):
    from cirno_core.bus.outbound_events import TurnEndEvent
    inbox.capture(OutboundMessage(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", content="",
        metadata={"webui_turn_id": "setup"}, event=TurnEndEvent(outcome="failed",
            failure_kind="model", failure_error_kind="configuration", failure_message="Configure a model")))
    assert inbox.list(category="conversations")["items"] == []
    notice = inbox.list(category="system")["items"][0]
    assert notice["kind"] == "turn"
    assert notice["body"] == "Configure a model"
