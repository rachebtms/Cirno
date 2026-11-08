"""Keep Dream work attached to its durable batch lease."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from pathlib import Path
from typing import TypeVar

from cirno_core.utils.cancellation import shield_and_drain

_Result = TypeVar("_Result")
_RENEW_INTERVAL_SECONDS = 60


def _renew(home: Path, token: str) -> None:
    from cirno_memory.repository import MemoryRepository

    if not MemoryRepository(home).renew(token):
        raise RuntimeError("Dream batch lease is no longer owned")


async def run_with_dream_lease(coro: Awaitable[_Result], token: str, home: Path) -> _Result:
    """Stop the run if renewal fails; drain both tasks on completion or cancellation."""
    async def renew() -> None:
        while True:
            await asyncio.sleep(_RENEW_INTERVAL_SECONDS)
            await shield_and_drain(asyncio.to_thread(_renew, home, token))

    operation = asyncio.ensure_future(coro)
    renewal = asyncio.create_task(renew())
    try:
        done, _ = await asyncio.wait({operation, renewal}, return_when=asyncio.FIRST_COMPLETED)
        if renewal in done:
            renewal.result()
        return await operation
    finally:
        operation.cancel()
        renewal.cancel()
        await asyncio.gather(operation, renewal, return_exceptions=True)
