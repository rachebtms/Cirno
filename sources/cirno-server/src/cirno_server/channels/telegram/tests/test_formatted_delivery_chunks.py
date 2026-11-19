"""Nonstream Telegram replies use the same rendered bounds as stream commits."""

import re
from html import unescape
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.bus.queue import MessageBus

from cirno_server.channels.telegram.formatting import (
    markdown_to_telegram_html,
    split_telegram_markdown_html_chunks,
    telegram_html_text_length,
)
from cirno_server.channels.telegram.limits import TELEGRAM_HTML_MAX_LEN
from cirno_server.channels.telegram.runtime import TelegramChannel


@pytest.mark.parametrize("blockquote,content", [
    (False, "<&>" * 1500), (True, "<&>" * 500),
    (False, "```text\n" + "<&>" * 1500 + "\n```"),
])
async def test_regular_reply_and_tool_hint_are_bounded_after_rendering(
    telegram_owner, blockquote, content
):
    channel = TelegramChannel(
        {"token": "test", "rich_messages": False, "inline_keyboards": True}, MessageBus()
    )
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    event = ProgressEvent(tool_hint=True) if blockquote else None
    await channel.send(OutboundMessage(
        "telegram", "123", content, event=event, buttons=[["Open", "Cancel"]]
    ))
    payloads = [call.kwargs for call in bot.send_message.await_args_list]
    assert len(payloads) == (1 if blockquote else 2)
    assert all(payload["parse_mode"] == "HTML" for payload in payloads)
    assert all(telegram_html_text_length(payload["text"]) <= TELEGRAM_HTML_MAX_LEN for payload in payloads)
    assert all(bool(payload.get("reply_markup")) is (index == len(payloads) - 1)
               for index, payload in enumerate(payloads))
    decoded = "".join(unescape(re.sub(r"<[^>]*>", "", payload["text"])) for payload in payloads)
    for character in "<&>":
        assert decoded.count(character) == content.count(character)
    if blockquote:
        assert all(payload["text"].startswith("<blockquote expandable>") for payload in payloads)


def test_entity_and_tag_spelling_does_not_force_extra_messages():
    content = "<&>" * 500
    rendered = markdown_to_telegram_html(content)
    assert len(rendered) > TELEGRAM_HTML_MAX_LEN
    assert telegram_html_text_length(rendered) == len(content)
    assert split_telegram_markdown_html_chunks(content, TELEGRAM_HTML_MAX_LEN) == [(content, rendered)]


async def test_table_expansion_is_bounded_in_regular_delivery(telegram_owner):
    content = "|" + "W" * 120 + "|Value|\n|---|---|\n" + "\n".join(
        f"|row{index:03d}|x|" for index in range(80)
    )
    assert len(content) < TELEGRAM_HTML_MAX_LEN
    assert telegram_html_text_length(markdown_to_telegram_html(content)) > TELEGRAM_HTML_MAX_LEN
    channel = TelegramChannel({"token": "test", "rich_messages": False}, MessageBus())
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
    channel.connection.app = SimpleNamespace(bot=bot)
    channel.connection.ready.set()
    await channel.send(OutboundMessage("telegram", "123", content))
    sent = [call.kwargs["text"] for call in bot.send_message.await_args_list]
    assert len(sent) > 1
    assert all(telegram_html_text_length(text) <= TELEGRAM_HTML_MAX_LEN for text in sent)
    combined = "".join(sent)
    assert all(combined.count(f"row{index:03d}") == 1 for index in range(80))
