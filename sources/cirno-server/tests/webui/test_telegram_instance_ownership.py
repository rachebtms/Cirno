"""Telegram settings and forwarding retain the instance that admitted them."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import set_config_path
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_server.channels.delivery.publish import publish_to_channel
from cirno_server.channels.telegram.binding import TelegramBinding
from cirno_server.webui.instance_api import instance_action


def bind(state, identifier):
    owner = TelegramBinding(state)
    pin = owner.issue_pin()
    assert owner.verify(pin["pin"], user_id=identifier, chat_id=identifier)
    return owner


@pytest.mark.parametrize("action", ["status", "pin", "settings", "unbind"])
async def test_telegram_http_action_uses_its_server_config(tmp_path, action):
    first, second = tmp_path / "first", tmp_path / "second"
    original, unrelated = bind(first / "state", 123), bind(second / "state", 456)
    set_config_path(second / "config.json")
    result = await instance_action(
        {"action": "telegram." + action, "values": {"enabled": False} if action == "settings" else {}},
        sessions=None, bus=None, config_path=first / "config.json",
    )
    if action == "status":
        assert result["chat_id"] == "123"
    elif action == "pin":
        assert original.verify(result["pin"], user_id=123, chat_id=123)
    elif action == "settings":
        assert not original.status()["enabled"]
        assert unrelated.status()["enabled"]
    else:
        assert not original.status()["bound"]
        assert unrelated.status()["bound"]


async def test_router_forwarding_keeps_its_admitted_config_across_history_write(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    bind(first / "state", 123)
    bind(second / "state", 456)
    set_config_path(first / "config.json")
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    await sessions.state.import_messages(ROUTER_SESSION_KEY, [{"role": "user", "content": "Fixture"}])
    original = sessions.state.record_delivery

    async def write(*args, **kwargs):
        set_config_path(second / "config.json")
        return await original(*args, **kwargs)

    monkeypatch.setattr(sessions.state, "record_delivery", write)
    bus = MessageBus()
    try:
        await publish_to_channel(OutboundMessage("websocket", ROUTER_SESSION_KEY.split(":", 1)[1], "Fixture result"),
                                 bus=bus, session_manager=sessions, record=True)
        assert bus.outbound_size == 2
        await bus.consume_outbound()
        forwarded = await bus.consume_outbound()
        assert forwarded.channel == "telegram" and forwarded.chat_id == "123"
    finally:
        await sessions.state.aclose()


async def test_telegram_runtime_and_stream_use_their_original_binding(tmp_path):
    pytest.importorskip("telegram")
    from cirno_core.bus.delivery import DeliveryRejectedError
    from cirno_server.channels.telegram.runtime import TelegramChannel

    first, second = tmp_path / "first", tmp_path / "second"
    original = bind(first / "state", 123)
    bind(second / "state", 456)
    set_config_path(first / "config.json")
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    set_config_path(second / "config.json")
    assert await channel.check_sender("123")
    assert not await channel.check_sender("456")
    channel.connection.wait_for_app = AsyncMock(return_value=None)
    metadata = {"_telegram_binding": original.status()["id"], "_telegram_category": "router"}
    with pytest.raises(DeliveryRejectedError):
        await channel.send_delta("456", "Do not send", metadata)
    channel.connection.wait_for_app.assert_not_awaited()


async def test_telegram_binding_verification_stays_in_the_channel_instance(tmp_path):
    pytest.importorskip("telegram")
    from cirno_server.channels.telegram.runtime import TelegramChannel

    first, second = tmp_path / "first", tmp_path / "second"
    original, unrelated = TelegramBinding(first / "state"), TelegramBinding(second / "state")
    pin = original.issue_pin()
    unrelated.issue_pin()
    inboxes = [NotificationInbox(path / "state") for path in (first, second)]
    for inbox in inboxes:
        inbox.record("fixture-action", "operations", "approval", status="pending")
        item = inbox.telegram_pending()[0]
        inbox.telegram_queued(item["id"], item["revision"])
    set_config_path(first / "config.json")
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    set_config_path(second / "config.json")
    message = SimpleNamespace(text="/bind " + pin["pin"], chat_id=123, reply_text=AsyncMock())
    assert await channel._try_bind(message=message, user=SimpleNamespace(id=123, username="fixture", language_code="en"))
    assert original.status()["bound"] and not unrelated.status()["bound"]
    assert len(inboxes[0].telegram_pending()) == 1
    assert inboxes[1].telegram_pending() == []


async def test_telegram_media_download_retains_the_channel_state_directory(tmp_path):
    pytest.importorskip("telegram")
    from cirno_server.channels.telegram.runtime import TelegramChannel

    first, second = tmp_path / "first", tmp_path / "second"
    set_config_path(first / "config.json")
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    download = AsyncMock()
    channel.connection.app = SimpleNamespace(bot=SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=download)),
    ))
    set_config_path(second / "config.json")
    message = SimpleNamespace(photo=None, voice=None, audio=None, video=None, video_note=None, animation=None,
                              document=SimpleNamespace(file_id="fixture", file_unique_id="fixture", file_name="paper.pdf", mime_type="application/pdf"))
    paths, _ = await channel._download_message_media(message)
    assert paths == [str(first / "state" / "media" / "telegram" / "fixture.pdf")]
    download.assert_awaited_once_with(paths[0])
    assert not (second / "state").exists()


def test_telegram_factory_passes_its_gateway_state_directory(tmp_path):
    pytest.importorskip("telegram")
    from cirno_core.config.schema import Config
    from cirno_server.channels.factory import ChannelFactory
    from cirno_server.channels.telegram.config import TelegramConfig
    from cirno_server.channels.telegram.runtime import TelegramChannel

    first, second = tmp_path / "first", tmp_path / "second"
    set_config_path(second / "config.json")
    factory = ChannelFactory(MessageBus(), SimpleNamespace(config_path=first / "config.json"))
    channel = factory.build(Config(), TelegramChannel, TelegramConfig(token="fixture"))
    assert channel.binding.path == first / "state" / "telegram.sqlite3"
    assert channel.delivery.state_dir == channel.streams.state_dir == first / "state"


@pytest.mark.parametrize("transport", ["final", "stream"])
@pytest.mark.parametrize("recipient", ["123", "456"])
async def test_send_destination_uses_channel_owner_after_global_instance_changes(tmp_path, transport, recipient):
    pytest.importorskip("telegram")
    from cirno_core.bus.delivery import ChannelNotReadyError, DeliveryRejectedError
    from cirno_server.channels.telegram.runtime import TelegramChannel

    first, second = tmp_path / "first", tmp_path / "second"
    bind(first / "state", 123)
    bind(second / "state", 456)
    set_config_path(first / "config.json")
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    channel.connection.wait_for_app = AsyncMock(return_value=None)
    set_config_path(second / "config.json")
    error = ChannelNotReadyError if recipient == "123" else DeliveryRejectedError
    with pytest.raises(error):
        if transport == "final":
            await channel.send(OutboundMessage("telegram", recipient, "Fixture"))
        else:
            await channel.send_delta(recipient, "Fixture")
    assert channel.connection.wait_for_app.await_count == (1 if recipient == "123" else 0)
