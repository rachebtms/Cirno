"""A hard cut cannot turn a continuation into a fresh Markdown block."""

import re
from html import unescape
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")

from cirno_core.bus.queue import MessageBus
from telegram.error import BadRequest

from cirno_server.channels.telegram import limits
from cirno_server.channels.telegram.formatting import (
    markdown_to_telegram_html,
    split_telegram_markdown_html_chunks,
    strip_md_block,
)
from cirno_server.channels.telegram.rich import TelegramRichMessages
from cirno_server.channels.telegram.runtime import TelegramChannel


def shown(html):
    return unescape(re.sub(r"<[^>]*>", "", html))


@pytest.mark.parametrize("suffix", [">tail", "# title", "- item", "1.  item"])
def test_hard_cut_does_not_reinterpret_the_first_continuation_line(monkeypatch, suffix):
    monkeypatch.setattr(limits, "TELEGRAM_MAX_MESSAGE_LEN", 16)
    monkeypatch.setattr("cirno_server.channels.telegram.formatting.TELEGRAM_MAX_MESSAGE_LEN", 16)
    content = "A" * 16 + suffix
    chunks = split_telegram_markdown_html_chunks(content, 4096)
    actual = "".join(shown(html) for _, html in chunks)
    assert actual == content


async def test_preview_updates_and_finalization_retain_the_tail_line_context(
    telegram_owner, monkeypatch
):
    monkeypatch.setattr(limits, "TELEGRAM_MAX_MESSAGE_LEN", 16)
    monkeypatch.setattr("cirno_server.channels.telegram.formatting.TELEGRAM_MAX_MESSAGE_LEN", 16)
    channel = TelegramChannel({"token": "test", "rich_messages": False}, MessageBus())
    ids = iter(range(1, 20))
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=lambda **kwargs: SimpleNamespace(message_id=next(ids))),
        edit_message_text=AsyncMock(),
    )
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    await channel.send_delta("123", "A" * 16 + ">ta", stream_id="fixture")
    assert bot.send_message.await_args.kwargs["text"] == ">ta"
    assert channel.streams.buffers["123"].text == ">ta"
    channel.streams.buffers["123"].last_edit = 0
    await channel.send_delta("123", "il", stream_id="fixture")
    assert bot.edit_message_text.await_args.kwargs["text"] == ">tail"
    await channel.send_delta("123", "", stream_id="fixture", stream_end=True)
    assert shown(bot.edit_message_text.await_args.kwargs["text"]) == ">tail"
    assert "123" not in channel.streams.buffers


def test_real_newlines_still_start_markdown_blocks(monkeypatch):
    monkeypatch.setattr("cirno_server.channels.telegram.formatting.TELEGRAM_MAX_MESSAGE_LEN", 16)
    chunks = split_telegram_markdown_html_chunks("A" * 16 + ">literal\n>quote", 4096)
    assert "".join(shown(html) for _, html in chunks) == "A" * 16 + ">literal\nquote"
    chunks = split_telegram_markdown_html_chunks("A" * 16 + "\n>quote", 4096)
    assert "".join(shown(html) for _, html in chunks) == "A" * 16 + "quote"


def test_adaptive_recuts_keep_the_original_line_context(monkeypatch):
    monkeypatch.setattr("cirno_server.channels.telegram.formatting.TELEGRAM_MAX_MESSAGE_LEN", 16)
    content = "A" * 16 + ">tail"
    chunks = split_telegram_markdown_html_chunks(content, 8)
    assert "".join(shown(html) for _, html in chunks) == content
    assert all(len(shown(html)) <= 8 for _, html in chunks)


def test_first_continuation_marker_cannot_hide_a_real_block_on_the_next_line():
    text = ">\n>quote"
    assert shown(markdown_to_telegram_html(text, line_continuation=True)) == ">\nquote"
    assert strip_md_block(text, line_continuation=True) == ">\nquote"


@pytest.mark.parametrize("prefix,escaped", [
    (">tail", "&#62;tail"), ("# title", "&#35; title"),
    ("- item", "&#45; item"), ("1. item", "&#49;. item"),
    ("**bold**", "**bold**"), ("[link](https://fixture.test)", "[link](https://fixture.test)"),
])
def test_native_rich_tail_preserves_media_math_and_other_markdown(prefix, escaped):
    rest = "\n![figure](https://fixture.test/a.png)\n$x^2$\n==highlight=="
    payload = TelegramRichMessages.rich_message_payload(prefix + rest, line_continuation=True)
    assert payload == {"markdown": escaped + rest}


def test_table_delimiter_without_a_header_does_not_reformat_following_text():
    text = "prefix |a|b|\n|-|-|\n|c|d|"
    assert shown(markdown_to_telegram_html(text)) == text


def test_formatted_table_keeps_an_empty_data_row():
    text = "|A|B|\n|---|---|\n| | |\n|C|D|"
    rows = shown(markdown_to_telegram_html(text)).splitlines()
    assert len(rows) == 4
    assert not rows[2].strip()


def test_formatted_table_keeps_an_empty_first_column():
    text = "|Left|Right|\n|---|---|\n||x|"
    rows = shown(markdown_to_telegram_html(text)).splitlines()
    assert rows[-1].startswith(" " * 6 + "x")


@pytest.mark.parametrize("fallback", [False, True])
async def test_rich_overflow_draft_and_final_tail_keep_continuation(
    telegram_owner, monkeypatch, fallback
):
    monkeypatch.setattr(limits, "TELEGRAM_RICH_MAX_LEN", 16)
    channel = TelegramChannel({"token": "test", "rich_messages": True}, MessageBus())

    async def request(method, *, api_kwargs):
        if fallback and method == "sendRichMessageDraft" and api_kwargs["rich_message"]["markdown"].startswith("&#"):
            raise BadRequest("unsupported rich draft")
        return {}

    bot = SimpleNamespace(
        do_api_request=AsyncMock(side_effect=request),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=4)),
        edit_message_text=AsyncMock(),
    )
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    await channel.send_delta("123", "A" * 16, stream_id="fixture")
    channel.streams.buffers["123"].last_edit = 0
    await channel.send_delta("123", ">ta", stream_id="fixture")
    assert channel.streams.buffers["123"].text == ">ta"
    assert channel.streams.buffers["123"].line_continuation
    channel.streams.buffers["123"].last_edit = 0
    await channel.send_delta("123", "il", stream_id="fixture")
    await channel.send_delta("123", "", stream_id="fixture", stream_end=True)
    if fallback:
        assert shown(bot.edit_message_text.await_args.kwargs["text"]) == ">tail"
    else:
        payload = bot.do_api_request.await_args.kwargs["api_kwargs"]["rich_message"]
        assert payload == {"markdown": "&#62;tail"}
        bot.send_message.assert_not_awaited()
    assert "123" not in channel.streams.buffers


async def test_rejected_later_chunk_keeps_unmodified_resume_source(telegram_owner, monkeypatch):
    monkeypatch.setattr(limits, "TELEGRAM_MAX_MESSAGE_LEN", 8)
    monkeypatch.setattr("cirno_server.channels.telegram.formatting.TELEGRAM_MAX_MESSAGE_LEN", 8)
    channel = TelegramChannel({"token": "test", "rich_messages": False}, MessageBus())
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=[
            SimpleNamespace(message_id=1), SimpleNamespace(message_id=2), BadRequest("rejected"),
        ]), edit_message_text=AsyncMock(),
    )
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    with pytest.raises(BadRequest, match="rejected"):
        await channel.send_delta("123", "A" * 8 + ">tail" + "b" * 8, stream_id="fixture")
    buf = channel.streams.buffers["123"]
    assert buf.text == ">tail" + "b" * 8
    assert buf.message_id == 2 and buf.line_continuation
    bot.send_message.side_effect = None
    bot.send_message.return_value = SimpleNamespace(message_id=3)
    await channel.send_delta("123", "", stream_id="fixture", stream_end=True)
    assert shown(bot.edit_message_text.await_args.kwargs["text"]) == ">tailbbb"
    assert shown(bot.send_message.await_args.kwargs["text"]) == "b" * 5
    assert "123" not in channel.streams.buffers
