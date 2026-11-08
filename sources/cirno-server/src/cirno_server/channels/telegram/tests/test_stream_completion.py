"""Finalization preserves long-message tails and reports uncertain delivery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.telegram.formatting import split_telegram_markdown_html_chunks
from cirno_server.channels.telegram.runtime import TelegramChannel
from cirno_server.channels.telegram.state import StreamBuf
from telegram.error import BadRequest, TimedOut


def ready_channel(*, rich=False):
    channel = TelegramChannel({"token": "test", "rich_messages": rich}, MessageBus())
    bot = SimpleNamespace(
        edit_message_text=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=8)),
        do_api_request=AsyncMock(),
    )
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    return channel, bot


async def test_unchanged_primary_still_delivers_remaining_chunks(telegram_owner, monkeypatch):
    monkeypatch.setattr("cirno_server.channels.telegram.limits.TELEGRAM_HTML_MAX_LEN", 24)
    channel, bot = ready_channel()
    bot.edit_message_text.side_effect = BadRequest("Message is not modified")
    channel.streams.buffers["123"] = StreamBuf(text="A" * 24 + "\n" + "B" * 24, message_id=7)

    await channel.send_delta("123", "", stream_end=True)

    chunks = split_telegram_markdown_html_chunks("A" * 24 + "\n" + "B" * 24, 24)
    assert [call.kwargs["text"] for call in bot.send_message.await_args_list] == [
        html for _, html in chunks[1:]
    ]
    assert "123" not in channel.streams.buffers


async def test_cancelled_new_message_has_an_unknown_outcome(telegram_owner):
    channel, bot = ready_channel(rich=True)
    entered = asyncio.Event()

    async def submit(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    bot.do_api_request.side_effect = submit
    channel.streams.buffers["123"] = StreamBuf(
        text="final result",
        draft_id=17,
        stream_id="s:0",
    )
    send = asyncio.create_task(channel.send_delta("123", "", stream_id="s:0", stream_end=True))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
    finally:
        send.cancel()
        with pytest.raises(asyncio.CancelledError):
            await send

    bot.do_api_request.side_effect = None
    with pytest.raises(RuntimeError, match="delivery.*unknown"):
        await channel.send_delta("123", "", stream_id="s:0", stream_end=True)
    bot.do_api_request.assert_awaited_once()


async def test_final_html_rejection_falls_back_to_raw_chunk_without_losing_tail(
    telegram_owner,
    monkeypatch,
):
    monkeypatch.setattr("cirno_server.channels.telegram.limits.TELEGRAM_HTML_MAX_LEN", 30)
    channel, bot = ready_channel()
    # The primary is unchanged in plain text; all later chunks still need delivery.
    bot.edit_message_text.side_effect = [
        BadRequest("Can't parse entities"),
        BadRequest("Message is not modified"),
    ]
    bot.send_message.side_effect = [
        BadRequest("Can't parse entities"),
        SimpleNamespace(message_id=8),
    ]
    channel.streams.buffers["123"] = StreamBuf(
        text="A" * 24 + "\n**tail**",
        message_id=7,
    )

    await channel.send_delta("123", "", stream_end=True)

    assert bot.send_message.await_args.kwargs["text"].endswith("**tail**")
    assert "parse_mode" not in bot.send_message.await_args.kwargs
    assert "123" not in channel.streams.buffers


@pytest.mark.parametrize("rich", [False, True])
async def test_unknown_stream_send_is_reported_and_never_replayed(
    rich, telegram_owner, monkeypatch
):
    monkeypatch.setattr("cirno_server.channels.telegram.api._SEND_RETRY_BASE_DELAY", 0)
    monkeypatch.setattr("cirno_server.channels.telegram.limits.TELEGRAM_HTML_MAX_LEN", 24)
    channel, bot = ready_channel(rich=rich)
    text = "A" * 24 + "\n" + "B" * 24
    channel.streams.buffers["123"] = StreamBuf(
        text=text,
        message_id=None if rich else 7,
        draft_id=17 if rich else None,
        stream_id="s:0",
    )
    sender = bot.do_api_request if rich else bot.send_message
    sender.side_effect = TimedOut("delivery unknown")

    with pytest.raises(TimedOut, match="delivery unknown"):
        await channel.send_delta("123", "", stream_id="s:0", stream_end=True)
    sender.assert_awaited_once()
    assert "123" in channel.streams.buffers

    with pytest.raises(RuntimeError, match="delivery.*unknown"):
        await channel.send_delta("123", "", stream_id="s:0", stream_end=True)
    with pytest.raises(RuntimeError, match="delivery.*unknown"):
        await channel.send_delta("123", "more", stream_id="s:0")
    sender.assert_awaited_once()

    # A later model response owns a new stream and can deliver independently.
    bot.do_api_request.side_effect = None
    bot.send_message.side_effect = None
    bot.send_message.return_value = SimpleNamespace(message_id=9)
    await channel.send_delta("123", "next response", stream_id="s:1")
    await channel.send_delta("123", "", stream_id="s:1", stream_end=True)
    assert "123" not in channel.streams.buffers
