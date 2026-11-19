"""Serialized thread I/O whose ownership lasts through physical settlement."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from cirno_core.utils.cancellation import shield_and_drain

_P = ParamSpec("_P")
_T = TypeVar("_T")


class SerializedThreadIO:
    """One lock per storage owner, using the event loop's existing thread pool.

    Waiting for admission is cancellable. Once admitted, an operation settles
    before cancellation propagates and before the next caller gets the lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def __call__(
        self, operation: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs,
    ) -> _T:
        async with self._lock:
            return await shield_and_drain(asyncio.to_thread(operation, *args, **kwargs))
