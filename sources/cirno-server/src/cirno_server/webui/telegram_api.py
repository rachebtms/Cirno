"""Personal Telegram binding operations without blocking the Web UI loop."""

from __future__ import annotations

import asyncio

from cirno_core.utils.cancellation import shield_and_drain
from cirno_server.channels.telegram.binding import TelegramBinding

_METHODS = {
    "telegram.status": "status",
    "telegram.pin": "issue_pin",
    "telegram.settings": "update",
    "telegram.unbind": "unbind",
}


async def telegram_action(action: str, values: dict) -> dict:
    try:
        method = _METHODS[action]
    except KeyError:
        raise ValueError("Unknown Telegram binding action") from None

    def execute():
        operation = getattr(TelegramBinding(), method)
        return operation(values) if method == "update" else operation()

    worker = asyncio.to_thread(execute)
    return await worker if method == "status" else await shield_and_drain(worker)
