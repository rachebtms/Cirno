"""Binding persistence, event-loop responsiveness and accepted write ownership."""

import asyncio
from threading import Event

import pytest
from cirno_server.channels.telegram.binding import TelegramBinding
from cirno_server.webui import telegram_api
from cirno_server.webui.instance_api import instance_action


@pytest.mark.asyncio
async def test_personal_binding_round_trip(tmp_path, monkeypatch):
    binding = TelegramBinding(tmp_path)
    monkeypatch.setattr(telegram_api, "TelegramBinding", lambda: binding)

    async def action(name, **values):
        return await instance_action({"action": f"telegram.{name}", "values": values}, sessions=None, bus=None)

    assert not (await action("status"))["bound"]
    pin = await action("pin")
    assert binding.verify(pin["pin"], user_id=123, chat_id=123, username="owner")
    assert (await action("status"))["username"] == "owner"
    await action("settings", enabled=False, notifications=["operations"], webui_url="https://cirno.example")
    disconnected = await action("unbind")
    assert not disconnected["bound"]
    assert disconnected["notifications"] == ["operations"]
    assert not disconnected["enabled"]
    assert disconnected["webui_url"] == "https://cirno.example"
    with pytest.raises(ValueError, match="Unknown Telegram"):
        await action("invalid")


@pytest.mark.asyncio
async def test_slow_sqlite_read_does_not_block_ui_loop(monkeypatch):
    released = Event()

    def status(self):
        assert released.wait(1), "binding read blocked the event loop"
        return {"bound": False}

    monkeypatch.setattr(TelegramBinding, "status", status)
    timer = asyncio.get_running_loop().call_later(0.02, released.set)
    try:
        assert await telegram_api.telegram_action("telegram.status", {}) == {"bound": False}
    finally:
        released.set()
        timer.cancel()


@pytest.mark.asyncio
async def test_accepted_write_settles_before_cancellation_returns(monkeypatch):
    started, released, completed = Event(), Event(), Event()

    def update(self, values):
        started.set()
        assert released.wait(2)
        completed.set()
        return values

    monkeypatch.setattr(TelegramBinding, "update", update)
    task = asyncio.create_task(telegram_api.telegram_action("telegram.settings", {"enabled": False}))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        released.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed.is_set()
    finally:
        released.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_storage_failure_reaches_caller(monkeypatch):
    def status(self):
        raise OSError("binding database unavailable")

    monkeypatch.setattr(TelegramBinding, "status", status)
    with pytest.raises(OSError, match="binding database unavailable"):
        await telegram_api.telegram_action("telegram.status", {})
