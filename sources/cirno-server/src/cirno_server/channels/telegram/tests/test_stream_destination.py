"""Streaming uses the same personal-account policy as final message delivery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")

from cirno_core.bus.delivery import DeliveryRejectedError
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.telegram.binding import TelegramBinding
from cirno_server.channels.telegram.runtime import TelegramChannel


@pytest.mark.parametrize("case", ["other-account", "muted", "old-binding", "group", "unbound"])
async def test_stream_rejects_changed_or_nonpersonal_destination(monkeypatch, case):
    status = {"bound": True, "enabled": True, "chat_id": "123", "id": "new", "notifications": ["router"]}
    chat_id, metadata = "123", {}
    if case == "other-account":
        chat_id = "456"
    elif case == "muted":
        status["enabled"] = False
    elif case == "old-binding":
        metadata = {"_telegram_binding": "old", "_telegram_category": "router"}
    elif case == "group":
        status["bound"] = False
        chat_id = "-100123"
    else:
        status["bound"] = False
    monkeypatch.setattr(TelegramBinding, "status", lambda self: status)
    channel = TelegramChannel({"token": "test"}, MessageBus())
    channel.connection.wait_for_app = AsyncMock(return_value=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())))
    with pytest.raises(DeliveryRejectedError):
        await channel.send_delta(chat_id, "Private result", metadata, stream_id="one")
    channel.connection.wait_for_app.assert_not_awaited()
    assert channel.streams.buffers == {}
