"""Blocking safety/file checks cannot freeze channel or browser controls."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.runtime.admission import RuntimeAdmission
from cirno_server.channels.telegram import delivery
from cirno_server.channels.telegram.config import TelegramConfig
from cirno_server.webui.mcp import oauth_api


@pytest.mark.parametrize("boundary", ["telegram_url", "telegram_file", "mcp_oauth"])
async def test_delivery_check_keeps_loop_responsive_and_cancel_does_not_send(monkeypatch, boundary):
    started, finished, release = threading.Event(), threading.Event(), threading.Event()

    def slow_check(*_args):
        started.set()
        try:
            release.wait(1)
            return b"fixture" if boundary == "telegram_file" else (False, "Blocked fixture")
        finally:
            finished.set()

    api = None
    if boundary == "mcp_oauth":
        monkeypatch.setattr(oauth_api, "validate_url_target", slow_check)
        manager = oauth_api.McpOAuthManager(RuntimeAdmission())
        flow = SimpleNamespace(error=None)
        operation = manager._receive_authorization_url(flow, "https://accounts.test/authorize?state=fixture")
    else:
        monkeypatch.setattr(delivery, "personal_chat_id", lambda _chat, _metadata, **_kwargs: 123)
        api = SimpleNamespace(connection=SimpleNamespace(wait_for_app=AsyncMock(return_value=MagicMock())),
                              call_with_retry=AsyncMock())
        sender = delivery.TelegramDelivery(api, MagicMock(), MagicMock(), TelegramConfig(), lambda: False)
        if boundary == "telegram_url":
            monkeypatch.setattr(delivery, "validate_url_target", slow_check)
            media = "https://example.test/image.png"
        else:
            monkeypatch.setattr(Path, "read_bytes", slow_check)
            media = "/tmp/fixture.pdf"
        operation = sender.send(OutboundMessage("telegram", "123", "", media=[media]))
    task = asyncio.create_task(operation)
    try:
        entered = await asyncio.to_thread(started.wait, 2)
        if not entered and task.done():
            await task  # Surface a fixture/setup failure before the liveness assertion.
        assert entered
        assert not finished.is_set(), "Channel validation/read blocked the event loop"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
        if api is not None:
            api.call_with_retry.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.to_thread(finished.wait, 2)
