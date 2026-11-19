"""Personal Telegram binding operations without blocking the Web UI loop."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cirno_core.config.loader import get_config_path
from cirno_core.utils.cancellation import shield_and_drain

from cirno_server.channels.telegram.binding import TelegramBinding

_METHODS = {
    "telegram.status": "status",
    "telegram.pin": "issue_pin",
    "telegram.settings": "update",
    "telegram.unbind": "unbind",
}


async def telegram_action(action: str, values: dict, *, config_path: Path | None = None) -> dict:
    try:
        method = _METHODS[action]
    except KeyError:
        raise ValueError("Unknown Telegram binding action") from None

    source = Path(config_path if config_path is not None else get_config_path()).expanduser().resolve(strict=False)

    def execute():
        operation = getattr(TelegramBinding(source.parent / "state"), method)
        return operation(values) if method == "update" else operation()

    worker = asyncio.to_thread(execute)
    # Status also initializes the SQLite schema on first use.
    return await shield_and_drain(worker)
