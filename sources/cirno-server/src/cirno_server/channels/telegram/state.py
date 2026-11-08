"""Telegram stream and ordered-input state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from telegram import Update
from telegram.ext import Application

TelegramApplication: TypeAlias = Application[Any, Any, Any, Any, Any, Any]


@dataclass
class StreamBuf:
    """Per-chat streaming accumulator for progressive message editing."""

    text: str = ""
    message_id: int | None = None
    draft_id: int | None = None
    last_edit: float = 0.0
    stream_id: str | None = None
    delivery_error: str | None = None

    def require_deliverable(self) -> None:
        if self.delivery_error is not None:
            raise RuntimeError(f"Telegram stream delivery is unknown: {self.delivery_error}")


@dataclass
class QueuedTelegramUpdate:
    """Telegram update staged for per-session ordered processing."""

    kind: Literal["command", "message"]
    update: Update
    sort_key: tuple[int, int]
