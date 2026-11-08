"""Personal Telegram binding, notification delivery and canonical Cirno routing."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.delivery import DeliveryRejectedError
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.bus.runtime_events import RuntimeEventPublisher
from cirno_core.config.home import set_instance_path
from cirno_core.config.schema import Config
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.session.manager import SessionManager
from cirno_core.session.router_session import ensure_router_session
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.publish import publish_to_channel
from cirno_server.channels.manager import ChannelManager
from cirno_server.channels.outbox import DeliveryOutbox
from cirno_server.channels.telegram.binding import TelegramBinding
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.channels.telegram.runtime import TelegramChannel


@pytest.fixture
async def personal(tmp_path):
    set_instance_path(tmp_path)
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    bus = MessageBus()
    yield tmp_path, sessions, bus
    await sessions.state.aclose()
    set_instance_path(None)


@pytest.fixture
async def delivery_manager(personal):
    home, sessions, bus = personal
    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    manager = ChannelManager(config, bus, session_manager=sessions, config_path=home / "config.json")
    manager.runtimes.channels["telegram"] = Mock(spec=BaseChannel, stop=AsyncMock())
    try:
        yield manager
    finally:
        await manager.stop_all()


def bind(home):
    binding = TelegramBinding(home / "state")
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=123, chat_id=123, username="owner")
    return binding


def test_pin_rotates_expires_is_single_use_and_limited(personal, monkeypatch):
    home, _, _ = personal
    binding = TelegramBinding(home / "state")
    old = binding.issue_pin()
    current = binding.issue_pin()
    assert not binding.verify(old["pin"], user_id=123, chat_id=123)
    assert binding.verify(current["pin"], user_id=123, chat_id=123)
    assert not binding.verify(current["pin"], user_id=456, chat_id=456)
    assert binding.status()["user_id"] == "123"
    expiring = binding.issue_pin()
    monkeypatch.setattr("cirno_server.channels.telegram.binding.time.time", lambda: expiring["expires_at"] / 1000 + 1)
    assert not binding.verify(expiring["pin"], user_id=456, chat_id=456)
    assert binding.status()["user_id"] == "123"


def test_pin_attempt_limit_and_group_rejection(personal):
    home, _, _ = personal
    binding = TelegramBinding(home / "state")
    pin = binding.issue_pin()
    for _ in range(10):
        assert not binding.verify("invalid", user_id=123, chat_id=123)
    assert not binding.verify(pin["pin"], user_id=123, chat_id=123)
    pin = binding.issue_pin()
    assert not binding.verify(pin["pin"], user_id=123, chat_id=-123)
    assert binding.verify(pin["pin"], user_id=123, chat_id=123)
    assert binding.path.stat().st_mode & 0o777 == 0o600


def test_unbind_revokes_legacy_allowlist_and_notification_preferences(personal):
    home, _, bus = personal
    binding = bind(home)
    channel = TelegramChannel(TelegramConfig(allow_from=["*"]), bus)
    assert channel.is_allowed("123|owner")
    assert not channel.is_allowed("456|stranger")
    binding.update({"notifications": ["operations"]})
    assert binding.destination("router") is None
    assert binding.destination("operations") is not None
    binding.update({"enabled": False})
    assert not channel.is_allowed("123|owner")
    binding.unbind()
    assert not channel.is_allowed("123|owner")
    assert not channel.is_allowed("456|stranger")


async def test_private_telegram_turn_uses_cirno_webui_execution_route(personal):
    _, sessions, bus = personal
    coordinator = WebuiTurnCoordinator(bus=bus, sessions=sessions, schedule_background=lambda task: None)
    with coordinator.connected():
        incoming = InboundMessage("telegram", "123", "123", "Hello", session_key_override="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
                                  metadata={"webui_turn_id": "telegram:test", "is_group": False})
        await RuntimeEventPublisher(bus).user_input_accepted(incoming, incoming.session_key)
        policy = WebuiTurnRoutePolicy(sessions)
        delivery = (await TurnDeliveryFactory(bus, policy, policy.admit).create(incoming, incoming.session_key, enable_stream=True))
        session = await sessions.state.get_header(incoming.session_key)
        await delivery.bind_session_generation(session.generation)
        assert delivery.streaming
        assert delivery.route.channel == "websocket" and delivery.route.chat_id == "b1ec9323-2155-5f24-bc56-1da2f59aeecb"
        assert delivery.route.metadata["_telegram_reply_to"] == "123"
        facts = await sessions.state.project_history(incoming.session_key, lambda history: history.all_facts())
        assert any(fact.content.get("text") == "Hello" for fact in facts)
        assert session.metadata["role"] == "router" and session.metadata["title"] == "@cirno"


async def test_cirno_replies_fan_out_once_without_recording_ordinary_inbox_messages(personal):
    home, sessions, bus = personal
    binding = bind(home)
    key = await ensure_router_session(sessions)
    header = await sessions.state.get_header(key)
    msg = OutboundMessage("websocket", "b1ec9323-2155-5f24-bc56-1da2f59aeecb", "Your answer", metadata={"_record_channel_delivery": True,
        "_session_key": key, "_session_generation": header.generation})
    await publish_to_channel(msg, bus=bus, session_manager=sessions)
    web, telegram = await bus.consume_outbound(), await bus.consume_outbound()
    assert web.channel == "websocket" and telegram.channel == "telegram"
    assert telegram.chat_id == "123"
    assert NotificationInbox.prepare(web) is None and NotificationInbox.prepare(telegram) is None
    assert telegram.metadata["_telegram_binding"] == binding.status()["id"]
    binding.update({"notifications": ["operations"]})
    await publish_to_channel(msg, bus=bus, session_manager=sessions)
    assert bus.outbound_size == 1


async def test_inbox_actions_use_durable_delivery_and_respect_category_mutes(personal, delivery_manager):
    home, sessions, bus = personal
    binding = bind(home)
    binding.update({"notifications": ["operations"], "webui_url": "https://cirno.example.com"})
    await ensure_router_session(sessions)
    inbox = NotificationInbox(home / "state")
    inbox.record("q", "operations", "question", status="pending", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", body="Choose?", data={"options": ["A", "B"]})
    inbox.record("c", "system", "compaction", body="Compacted")
    manager = delivery_manager
    manager.notifications.inbox = inbox
    await manager.notifications.queue_telegram()
    notification = await bus.consume_outbound()
    assert "Choose?" in notification.content and "1. A" in notification.content
    assert notification.delivery.run_id.startswith("inbox:" + binding.status()["id"] + ":q:")
    assert notification.metadata["_telegram_action_url"].startswith("https://cirno.example.com/#/inbox?")
    assert bus.outbound_size == 0 and inbox.telegram_pending() == []
    # Recover the accepted notification after a service restart.
    recovered = DeliveryOutbox(manager.delivery.durable.outbox.path).ready()
    assert len(recovered) == 1 and recovered[0].content == notification.content
    # A crash after outbox admission but before queue acknowledgement cannot duplicate it.
    retry = replace(notification, delivery_id=None)
    manager.delivery.durable.record(retry)
    assert retry.delivery_id == notification.delivery_id
    assert len(manager.delivery.durable.outbox.ready()) == 1
    # Identical records are not re-notified; genuine content/status changes are.
    inbox.record("q", "operations", "question", status="pending", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", body="Choose?", data={"options": ["A", "B"]})
    assert inbox.telegram_pending() == []
    inbox.record("q", "operations", "question", status="pending", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", body="Changed?")
    assert len(inbox.telegram_pending()) == 1


async def test_binding_command_is_consumed_before_authorization_or_model(personal):
    home, _, bus = personal
    code = TelegramBinding(home / "state").issue_pin()["pin"]
    channel = TelegramChannel(TelegramConfig(), bus)
    message = SimpleNamespace(text=f"/bind {code}", chat_id=123, chat=SimpleNamespace(type="private"), reply_text=AsyncMock())
    user = SimpleNamespace(id=123, username="owner", language_code="en")
    assert await channel._try_bind(message=message, user=user)
    assert channel.is_allowed("123|owner")
    assert bus.inbound_size == 0
    message.reply_text.assert_awaited_once_with("Connected to your Router.")


async def test_explicit_outbound_cannot_bypass_personal_binding_or_mute(personal):
    home, _, bus = personal
    binding = bind(home)
    channel = TelegramChannel(TelegramConfig(), bus)
    channel.connection.wait_for_app = AsyncMock()
    with pytest.raises(DeliveryRejectedError):
        await channel.send(OutboundMessage("telegram", "456", "Wrong recipient"))
    binding.update({"enabled": False})
    with pytest.raises(DeliveryRejectedError):
        await channel.send(OutboundMessage("telegram", "123", "Muted"))
    channel.connection.wait_for_app.assert_not_awaited()


async def test_full_notification_queue_does_not_prevent_recovering_accepted_deliveries(personal, delivery_manager):
    home, _, bus = personal
    manager = delivery_manager
    from cirno_core.bus.delivery import DeliveryRequest
    accepted = OutboundMessage("telegram", "123", "Already accepted", delivery=DeliveryRequest("run", "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", None))
    manager.delivery.durable.outbox.record(accepted)
    manager.notifications.queue_telegram = AsyncMock(side_effect=RuntimeError("queue full"))
    manager.delivery.queue = AsyncMock()
    manager.notifications.record = AsyncMock()
    with pytest.raises(RuntimeError, match="queue full"):
        await manager.dispatcher.recover()
    manager.delivery.queue.assert_awaited_once()
    assert manager.delivery.queue.await_args.args[1].delivery_id == accepted.delivery_id


async def test_notification_forwarding_failure_keeps_the_inbox_item_and_does_not_break_original_delivery(personal, delivery_manager):
    home, sessions, bus = personal
    await ensure_router_session(sessions)
    manager = delivery_manager
    manager.notifications.queue_telegram = AsyncMock(side_effect=RuntimeError("queue full"))
    question_id = "f" * 32
    msg = OutboundMessage("websocket", "b1ec9323-2155-5f24-bc56-1da2f59aeecb", "Choose?", metadata={"_agent_ui": {
        "kind": "user_question", "data": {"id": question_id, "question": "Choose?", "options": ["A", "B"]},
    }})
    await manager.notifications.record(msg)
    assert manager.notifications.inbox.get("question:" + question_id)["status"] == "pending"
    assert len(manager.notifications.inbox.telegram_pending()) == 1


async def test_router_binding_read_does_not_block_other_conversations(personal, monkeypatch):
    import asyncio
    import threading

    _, sessions, bus = personal
    await ensure_router_session(sessions)
    entered, release = threading.Event(), threading.Event()

    def blocked_destination(self, category):
        entered.set()
        release.wait(2)
        return None

    monkeypatch.setattr(TelegramBinding, "destination", blocked_destination)
    message = OutboundMessage("websocket", "b1ec9323-2155-5f24-bc56-1da2f59aeecb", "Answer")
    send = asyncio.create_task(publish_to_channel(message, bus=bus, session_manager=sessions, record=True))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        assert not send.done(), "Binding storage blocked the event loop until its read completed"
    finally:
        release.set()
        await send
