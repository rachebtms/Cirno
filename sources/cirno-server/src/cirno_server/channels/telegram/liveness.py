"""Telegram polling transport health observation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from telegram.request import BaseRequest


class _LivenessTrackedRequest(BaseRequest):
    """Wrap the getUpdates request pool, reporting each completed round trip."""

    __slots__ = ("inner", "_on_round_trip")

    def __init__(self, inner: BaseRequest, on_round_trip: Callable[[], None]) -> None:
        super().__init__()
        self.inner = inner
        self._on_round_trip = on_round_trip

    @property
    def read_timeout(self) -> float | None:
        return self.inner.read_timeout

    async def initialize(self) -> None:
        await self.inner.initialize()

    async def shutdown(self) -> None:
        await self.inner.shutdown()

    async def do_request(self, *args: Any, **kwargs: Any) -> tuple[int, bytes]:
        result = await self.inner.do_request(*args, **kwargs)
        self._on_round_trip()
        return result
