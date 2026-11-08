"""File I/O retains its worker until cancellation and writes have settled."""

import asyncio
from collections.abc import Callable
from threading import Event
from typing import TypeVar

from cirno_core.utils.cancellation import shield_and_drain

_T = TypeVar("_T")


async def run_file_operation(operation: Callable[[Event], _T]) -> _T:
    cancelled = Event()
    worker = asyncio.create_task(asyncio.to_thread(operation, cancelled))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled.set()
        try:
            await shield_and_drain(worker)
        finally:
            raise
