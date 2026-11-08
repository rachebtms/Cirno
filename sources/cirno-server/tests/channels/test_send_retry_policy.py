"""Reachable manager/adapter ownership contracts for outbound retries."""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

# Telegram is an optional channel dependency, as in its adapter-owned suite.
pytest.importorskip("telegram")
from cirno_core.bus.delivery import ChannelNotReadyError
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_server.channels.delivery import retry as retry_module
from cirno_server.channels.manager import ChannelManager
from cirno_server.channels.telegram import api as telegram_api
from cirno_server.channels.telegram.formatting import split_telegram_markdown
from cirno_server.channels.telegram.limits import TELEGRAM_MAX_MESSAGE_LEN
from cirno_server.channels.telegram.runtime import TelegramChannel
from telegram.error import NetworkError, RetryAfter, TimedOut


def make_manager(tmp_path):
    config = Config.model_validate({"channels": {"websocket": {"enabled": False}}})
    return ChannelManager(config, MessageBus(), config_path=tmp_path / "config.json")


def telegram_channel(manager):
    from cirno_server.channels.telegram.binding import TelegramBinding
    binding = TelegramBinding()
    pin = binding.issue_pin()
    assert binding.verify(pin["pin"], user_id=1, chat_id=1)
    channel = TelegramChannel({"token": "test", "rich_messages": False}, manager.bus)
    channel.connection.app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
    channel.connection.ready.set()
    return channel


async def test_telegram_exhausted_second_chunk_never_replays_successful_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(retry_module, "RETRY_DELAYS", (0,))
    monkeypatch.setattr(telegram_api, "_SEND_RETRY_BASE_DELAY", 0)
    manager = make_manager(tmp_path)
    channel = telegram_channel(manager)
    text = "a" * TELEGRAM_MAX_MESSAGE_LEN + "\n" + "b" * 20
    chunks = split_telegram_markdown(text, TELEGRAM_MAX_MESSAGE_LEN)
    assert len(chunks) == 2
    submitted = []

    async def send_message(**kwargs):
        submitted.append(kwargs["text"])
        if kwargs["text"] != chunks[0]:
            raise TimedOut("second part exhausted")
        return SimpleNamespace(message_id=1)

    channel.connection.app.bot.send_message.side_effect = send_message
    await manager.delivery.retry.send(channel, OutboundMessage("telegram", "1", text))
    assert submitted == [chunks[0], chunks[1]]


@pytest.mark.parametrize(("error", "requests"), [
    (TimedOut("timeout"), 1),
    (RetryAfter(0), 3),
    (NetworkError("ambiguous transport error"), 1),
    (RuntimeError("unknown send result"), 1),
])
async def test_telegram_manager_does_not_multiply_part_retry_budget(tmp_path, monkeypatch, error, requests):
    monkeypatch.setattr(retry_module, "RETRY_DELAYS", (0,))
    monkeypatch.setattr(telegram_api, "_SEND_RETRY_BASE_DELAY", 0)
    manager = make_manager(tmp_path)
    channel = telegram_channel(manager)
    channel.connection.app.bot.send_message.side_effect = error
    await manager.delivery.retry.send(channel, OutboundMessage("telegram", "1", "result"))
    assert channel.connection.app.bot.send_message.await_count == requests


async def test_telegram_manager_retries_only_pre_submit_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(retry_module, "RETRY_DELAYS", (0,))
    manager = make_manager(tmp_path)
    channel = telegram_channel(manager)
    channel.connection.wait_for_app = AsyncMock(side_effect=[None, channel.connection.app])
    await manager.delivery.retry.send(channel, OutboundMessage("telegram", "1", "result"))
    assert channel.connection.wait_for_app.await_count == 2
    channel.connection.app.bot.send_message.assert_awaited_once()


async def test_manager_equal_jitter_uses_capped_retry_delays(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    manager.runtimes.config.channels.send_max_retries = 6
    channel = SimpleNamespace(send=AsyncMock(side_effect=OSError("offline")),
                              should_retry_send_error=Mock(return_value=True))
    uniform = Mock(side_effect=lambda lower, upper: (lower + upper) / 2)
    monkeypatch.setattr(random, "uniform", uniform)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    await manager.delivery.retry.send(channel, OutboundMessage("test", "1", "result"))
    assert [call.args for call in uniform.call_args_list] == [(0.5, 1), (1.0, 2), (2.0, 4), (2.0, 4), (2.0, 4)]
    assert [call.args[0] for call in sleep.await_args_list] == [0.75, 1.5, 3, 3, 3]


async def test_manager_deadline_clamps_jitter_and_keeps_pre_submit_retry(tmp_path, monkeypatch):
    manager = make_manager(tmp_path)
    manager.runtimes.config.channels.send_max_retries = 1
    channel = SimpleNamespace(send=AsyncMock(side_effect=[ChannelNotReadyError("starting"), None]),
                              should_retry_send_error=Mock(return_value=True))
    monkeypatch.setattr(retry_module, "RETRY_DELAYS", (4,))
    monkeypatch.setattr(random, "uniform", lambda lower, upper: upper)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    await manager.delivery.retry.send(channel, OutboundMessage("test", "1", "result"),
                                   deadline=asyncio.get_running_loop().time() + 2)
    assert channel.send.await_count == 2
    assert 0 < sleep.await_args.args[0] <= 2


async def test_telegram_restart_notice_deadline_never_replays_unknown_result(tmp_path):
    from cirno_core.utils.restart import RestartNotice

    manager = make_manager(tmp_path)
    channel = telegram_channel(manager)
    channel.connection.running = True
    channel.connection.app.bot.send_message.side_effect = NetworkError("unknown delivery")
    manager.runtimes.channels["telegram"] = channel
    await manager._send_restart_notice_when_started(
        RestartNotice(channel="telegram", chat_id="1", started_at_raw=""), timeout_s=0.1,
    )
    channel.connection.app.bot.send_message.assert_awaited_once()
