"""Telegram storage cannot stall the loop or escape an accepted write owner."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.notifications.inbox import NotificationInbox
from cirno_server.channels.delivery.inbox import InboxDelivery
from cirno_server.channels.telegram.binding import TelegramBinding
from cirno_server.channels.telegram.runtime import TelegramChannel


@pytest.fixture
def isolated(tmp_path):
    set_instance_path(tmp_path)
    try:
        yield tmp_path
    finally:
        set_instance_path(None)


@pytest.mark.parametrize("path", ["binding-status", "binding-verify", "authorization", "base-authorization", "final-send", "stream-send"])
async def test_telegram_storage_wait_does_not_block_other_conversations(isolated, monkeypatch, path):
    released = threading.Event()
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    message = SimpleNamespace(text="Hello", chat_id=123, chat=SimpleNamespace(type="private"), reply_text=AsyncMock())
    user = SimpleNamespace(id=123, username="owner", first_name="Owner", language_code="en")
    update = SimpleNamespace(message=message, effective_user=user)
    status = {"bound": False, "enabled": True, "chat_id": "123", "user_id": "123"}

    def slow(*args, **kwargs):
        assert released.wait(0.5), "Telegram storage blocked the shared event loop"
        return False if path == "binding-verify" else status

    if path == "binding-verify":
        message.text = "/bind 12345678"
        monkeypatch.setattr(TelegramBinding, "verify", slow)
    else:
        monkeypatch.setattr(TelegramBinding, "status", slow)
    if path == "authorization":
        channel._try_bind = AsyncMock(return_value=False)
    # No Telegram transport: a missing application ends an allowed path locally.
    channel.connection.wait_for_app = AsyncMock(return_value=None)
    timer = asyncio.get_running_loop().call_later(0.01, released.set)
    try:
        if path.startswith("binding"):
            await channel._try_bind(message=message, user=user)
        elif path == "authorization":
            await channel._on_help(update, None)
        elif path == "base-authorization":
            await channel._handle_message("123|owner", "123", "Hello")
            assert channel.bus.inbound_size == 0
        else:
            from cirno_core.bus.delivery import DeliveryRejectedError
            with pytest.raises(DeliveryRejectedError):
                if path == "final-send":
                    await channel.send(OutboundMessage("telegram", "123", "Result"))
                else:
                    await channel.send_delta("123", "Result", stream_id="fixture")
    finally:
        released.set()
        timer.cancel()
    channel.connection.wait_for_app.assert_not_awaited()


@pytest.mark.parametrize("write", ["verify", "queue_pending_actions"])
async def test_binding_cancel_drains_verification_and_pending_action_writes(isolated, monkeypatch, write):
    entered, released, finished = threading.Event(), threading.Event(), threading.Event()
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    message = SimpleNamespace(text="/bind 12345678", chat_id=123, reply_text=AsyncMock())
    user = SimpleNamespace(id=123, username="owner", language_code="en")
    monkeypatch.setattr(TelegramBinding, "verify", lambda *args, **kwargs: True)
    queued = []
    monkeypatch.setattr(NotificationInbox, "queue_pending_actions", lambda self: queued.append(True))

    def blocked(*args, **kwargs):
        entered.set()
        assert released.wait(1)
        finished.set()
        if write == "queue_pending_actions":
            queued.append(True)
        return True

    owner = TelegramBinding if write == "verify" else NotificationInbox
    monkeypatch.setattr(owner, write, blocked)
    task = asyncio.create_task(channel._try_bind(message=message, user=user))
    try:
        assert await asyncio.to_thread(entered.wait, 1.5)
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        assert not task.done(), "Binding request abandoned an accepted writer"
    finally:
        released.set()
        await asyncio.gather(task, return_exceptions=True)
    assert finished.is_set() and queued == [True]
    assert task.cancelled()
    message.reply_text.assert_not_awaited()


async def test_cancelled_notice_capture_waits_for_the_durable_inbox_writer(isolated, monkeypatch):
    started, released, finished = threading.Event(), threading.Event(), threading.Event()
    bus = MessageBus()
    delivery = InboxDelivery(bus, isolated / "config.json", None, lambda name: None)
    original = NotificationInbox.record

    def record(self, **values):
        started.set()
        assert released.wait(2)
        try:
            return original(self, **values)
        finally:
            finished.set()

    monkeypatch.setattr(NotificationInbox, "record", record)
    message = OutboundMessage("websocket", "fixture", "Choose?", metadata={"_agent_ui": {
        "kind": "user_question", "data": {"id": "a" * 32, "question": "Choose?", "options": ["A"]},
    }})
    task = asyncio.create_task(delivery.record(message))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        assert not task.done(), "Notification capture abandoned its SQLite writer"
    finally:
        released.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
        delivery.close()
    assert task.cancelled()
    assert delivery.inbox.get("question:" + "a" * 32)["status"] == "pending"


@pytest.mark.parametrize("operation", ["answer", "telegram_pending", "telegram_queued"])
async def test_notification_queue_write_cancellation_retains_the_writer(isolated, monkeypatch, operation):
    from cirno_core.bus.runtime_events import RuntimeEventContext, UserInputAccepted

    started, released, finished = threading.Event(), threading.Event(), threading.Event()
    delivery = InboxDelivery(MessageBus(), isolated / "config.json", None, lambda name: object())
    identifier = "question:" + "a" * 32
    delivery.inbox.record(identifier, "operations", "question", session_key="websocket:fixture", status="pending", body="Choose?")
    state = {"bound": True, "enabled": False, "notifications": [], "bound_at": 0}
    monkeypatch.setattr(TelegramBinding, "status", lambda self: state)
    original = getattr(NotificationInbox, operation)

    def delayed(self, *args, **kwargs):
        started.set()
        assert released.wait(2)
        try:
            return original(self, *args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(NotificationInbox, operation, delayed)
    if operation == "answer":
        content = "> [!QUOTE]\n> <!-- cirno-question:" + "a" * 32 + " -->\n> Choose?\n\nA"
        action = delivery.answer(UserInputAccepted(RuntimeEventContext("websocket", "fixture", "websocket:fixture"), content))
    else:
        action = delivery.queue_telegram()
    task = asyncio.create_task(action)
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        assert not task.done(), f"{operation} released its writer early"
    finally:
        released.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
        delivery.close()
    assert task.cancelled()
    if operation == "answer":
        assert delivery.inbox.get(identifier)["status"] == "answered"
    elif operation == "telegram_queued":
        assert delivery.inbox.telegram_pending() == []
    else:
        assert len(delivery.inbox.telegram_pending()) == 1
