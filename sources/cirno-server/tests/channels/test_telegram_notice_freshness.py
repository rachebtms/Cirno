"""A queued Telegram notice must still represent the current Inbox action."""

import sqlite3
from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.notifications.inbox import NotificationInbox
from cirno_server.channels.delivery.durable import DurableDelivery
from cirno_server.channels.delivery.inbox import InboxDelivery
from cirno_server.channels.telegram.binding import TelegramBinding


@pytest.mark.parametrize("change", ["answered", "unavailable", "revised", "deleted"])
async def test_queued_telegram_notice_is_rejected_after_its_source_changes(tmp_path, change):
    pytest.importorskip("telegram")
    from cirno_server.channels.telegram.runtime import TelegramChannel

    state = tmp_path / "state"
    binding = TelegramBinding(state)
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=123, chat_id=123)
    inbox = NotificationInbox(state)
    identifier = "question:" + "a" * 32 if change == "answered" else "fixture"
    category, status = ("system", "info") if change == "revised" else ("operations", "pending")
    inbox.record(identifier, category, "question", status=status, session_key="websocket:fixture", body="Original")
    bus = MessageBus()
    durable = DurableDelivery(bus, tmp_path / "config.json", None, Config)
    channel = TelegramChannel({"token": "fixture"}, bus, state_dir=state)
    channel.connection.wait_for_app = AsyncMock(return_value=None)
    notifications = InboxDelivery(bus, tmp_path / "config.json", None, lambda _name: channel)
    try:
        await notifications.queue_telegram()
        assert bus.outbound_size == 1
        message = await bus.consume_outbound()
        if change == "answered":
            assert inbox.answer("websocket:fixture", "> [!QUOTE]\n> <!-- cirno-question:" + "a" * 32 + " -->\n> Question\n\nAnswer")
        elif change == "unavailable":
            inbox.unavailable(identifier)
        elif change == "revised":
            inbox.record(identifier, category, "question", status=status, session_key="websocket:fixture", body="New version")
        else:
            with inbox.connect() as db:
                db.execute("DELETE FROM notices WHERE id=?", (identifier,))
        await durable.send(channel, message)
        channel.connection.wait_for_app.assert_not_awaited()
        with sqlite3.connect(durable.outbox.path) as db:
            assert db.execute("SELECT status,error FROM deliveries").fetchone() == ("failed", "delivery_rejected")
    finally:
        notifications.close()


async def test_reading_an_unchanged_notice_does_not_invalidate_telegram_delivery(tmp_path):
    from cirno_server.channels.telegram.destination import personal_chat_id
    from cirno_server.channels.telegram.notifications import notification_message

    binding = TelegramBinding(tmp_path)
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=123, chat_id=123)
    inbox = NotificationInbox(tmp_path)
    inbox.record("fixture", "system", "fixture", body="Original")
    notice = inbox.telegram_pending()[0]
    message = notification_message(notice, binding.status())
    inbox.read(identifiers=["fixture"])
    assert personal_chat_id("123", message.metadata, state_dir=tmp_path) == 123


@pytest.mark.parametrize("resolved", [False, True])
def test_legacy_queued_action_without_content_revision_still_checks_pending_status(tmp_path, resolved):
    from cirno_core.bus.delivery import DeliveryRejectedError
    from cirno_server.channels.telegram.destination import personal_chat_id
    from cirno_server.channels.telegram.notifications import notification_message

    binding = TelegramBinding(tmp_path)
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=123, chat_id=123)
    inbox = NotificationInbox(tmp_path)
    inbox.record("fixture", "operations", "approval", status="pending", body="Action")
    notice = inbox.telegram_pending()[0]
    assert isinstance(notice["revision"], str)
    assert isinstance(notice["notice_revision"], int)
    message = notification_message(notice, binding.status())
    message.metadata.pop("_inbox_notice_revision")
    if resolved:
        inbox.unavailable("fixture")
        with pytest.raises(DeliveryRejectedError, match="resolved or replaced"):
            personal_chat_id("123", message.metadata, state_dir=tmp_path)
    else:
        assert personal_chat_id("123", message.metadata, state_dir=tmp_path) == 123
