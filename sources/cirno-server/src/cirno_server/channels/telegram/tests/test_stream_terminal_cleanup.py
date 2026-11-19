"""Terminal stream delivery preserves unsubmitted content and retires empty work."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("telegram")

from cirno_core.bus.queue import MessageBus
from telegram.error import BadRequest, TimedOut

from cirno_server.channels.telegram.runtime import TelegramChannel
from cirno_server.channels.telegram.state import StreamBuf


def channel_with_bot():
    channel = TelegramChannel({"token": "fixture"}, MessageBus())
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=7)),
        edit_message_text=AsyncMock(),
    )
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    channel.presence.stop_typing = Mock()
    channel.presence.remove_reaction = AsyncMock()
    return channel, bot


async def test_rejected_preview_does_not_silently_discard_the_final_reply(telegram_owner):
    channel, bot = channel_with_bot()
    bot.send_message.side_effect = [BadRequest("Preview rejected"), SimpleNamespace(message_id=7)]
    with pytest.raises(BadRequest, match="Preview rejected"):
        await channel.send_delta("123", "**Final result**", stream_id="turn:0")
    await channel.send_delta("123", "", stream_id="turn:0", stream_end=True)
    assert bot.send_message.await_count == 2
    assert bot.send_message.await_args.kwargs["text"] == "<b>Final result</b>"
    assert channel.streams.buffers == {}


@pytest.mark.parametrize("text", ["", " \n\t"])
async def test_empty_stream_end_retires_buffer_typing_and_reaction(text, telegram_owner):
    channel, bot = channel_with_bot()
    await channel.send_delta("123", text, stream_id="turn:0")
    await channel.send_delta("123", "", {"message_id": 11}, stream_id="turn:0", stream_end=True)
    assert channel.streams.buffers == {}
    channel.presence.stop_typing.assert_called_once_with("123")
    channel.presence.remove_reaction.assert_awaited_once_with("123", 11)
    bot.send_message.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()


async def test_old_terminal_event_does_not_clear_a_new_stream(telegram_owner):
    channel, bot = channel_with_bot()
    current = StreamBuf(text="new preview", message_id=7, stream_id="turn:1")
    channel.streams.buffers["123"] = current
    await channel.send_delta("123", "", stream_id="turn:0", stream_end=True)
    assert channel.streams.buffers == {"123": current}
    channel.presence.stop_typing.assert_not_called()
    bot.send_message.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()


async def test_empty_continuation_boundary_preserves_current_stream(telegram_owner):
    channel, bot = channel_with_bot()
    await channel.send_delta("123", " \n", stream_id="turn:0")
    current = channel.streams.buffers["123"]
    await channel.send_delta("123", "", stream_id="turn:0", stream_end=True, resuming=True, merge_next=True)
    assert channel.streams.buffers == {"123": current}
    channel.presence.stop_typing.assert_not_called()
    bot.send_message.assert_not_awaited()


async def test_unknown_initial_send_still_cannot_be_replayed_on_end(telegram_owner):
    channel, bot = channel_with_bot()
    bot.send_message.side_effect = TimedOut("outcome unknown")
    with pytest.raises(TimedOut, match="outcome unknown"):
        await channel.send_delta("123", "Final result", stream_id="turn:0")
    with pytest.raises(RuntimeError, match="delivery is unknown"):
        await channel.send_delta("123", "", stream_id="turn:0", stream_end=True)
    bot.send_message.assert_awaited_once()
