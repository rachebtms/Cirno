"""Unknown rich-message delivery must not submit a second plain-text copy."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.telegram.runtime import TelegramChannel
from telegram.error import NetworkError, TimedOut


@pytest.mark.parametrize(
    "error", [TimedOut("unknown result"), NetworkError("offline"), RuntimeError("transport failed")]
)
async def test_rich_send_unknown_result_is_reported_without_fallback(error, telegram_owner):
    channel = TelegramChannel({"token": "test", "rich_messages": True}, MessageBus())
    bot = SimpleNamespace(do_api_request=AsyncMock(side_effect=error), send_message=AsyncMock())
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    with pytest.raises(type(error), match=str(error)):
        await channel.send(OutboundMessage("telegram", "123", "Scientific result"))
    bot.do_api_request.assert_awaited_once()
    bot.send_message.assert_not_awaited()


async def test_media_failure_is_not_acknowledged_as_delivery(tmp_path, telegram_owner):
    channel = TelegramChannel({"token": "test"}, MessageBus())
    bot = SimpleNamespace(
        **{
            name: AsyncMock()
            for name in (
                "send_photo",
                "send_video",
                "send_voice",
                "send_audio",
                "send_document",
                "send_message",
            )
        }
    )
    bot.send_document.side_effect = TimedOut("file result unknown")
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    attachment = tmp_path / "report.txt"
    attachment.write_text("Scientific result")
    with pytest.raises(TimedOut, match="file result unknown"):
        await channel.send(OutboundMessage("telegram", "123", "", media=[str(attachment)]))
    bot.send_document.assert_awaited_once()


async def test_stopped_stream_is_not_acknowledged_as_delivery(telegram_owner):
    from cirno_core.bus.delivery import ChannelNotReadyError

    channel = TelegramChannel({"token": "test"}, MessageBus())
    with pytest.raises(ChannelNotReadyError):
        await channel.send_delta("123", "Scientific result", stream_id="s:0")
    assert not channel.streams.buffers


async def test_compaction_edit_outage_keeps_the_original_notice(
    tmp_path, telegram_owner, monkeypatch
):
    from cirno_core.bus.agent_events import ContextCompactionEvent

    monkeypatch.setattr("cirno_server.channels.telegram.api._SEND_RETRY_BASE_DELAY", 0)
    channel = TelegramChannel({"token": "test"}, MessageBus())
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=7)),
        edit_message_text=AsyncMock(side_effect=TimedOut("edit result unknown")),
    )
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()

    def notice(phase):
        return OutboundMessage(
            "telegram",
            "123",
            phase,
            event=ContextCompactionEvent(
                compaction_id="c1",
                phase=phase,
                notify=True,
            ),
        )

    await channel.send(notice("started"))
    with pytest.raises(TimedOut, match="edit result unknown"):
        await channel.send(notice("succeeded"))
    bot.send_message.assert_awaited_once()
    assert channel.delivery.compaction.messages == {("123", "c1"): 7}

    bot.edit_message_text.side_effect = None
    await channel.send(notice("succeeded"))
    bot.send_message.assert_awaited_once()
    assert not channel.delivery.compaction.messages
