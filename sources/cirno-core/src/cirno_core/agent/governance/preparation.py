"""Serialize physical prompt workers while allowing immediate cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import copy_context
from typing import ParamSpec, TypeVar

_PreparationArgs = ParamSpec("_PreparationArgs")
_PreparationResult = TypeVar("_PreparationResult")


class PromptPreparation:
    def __init__(self) -> None:
        self._preparation_slots = asyncio.Semaphore(1)
        self._preparation_jobs: set[Awaitable[object]] = set()

    async def run(
        self,
        operation: Callable[_PreparationArgs, _PreparationResult],
        *args: _PreparationArgs.args,
        **kwargs: _PreparationArgs.kwargs,
    ) -> _PreparationResult:
        """Run context preparation with one physical worker at a time."""
        await self._preparation_slots.acquire()
        context = copy_context()

        def prepare() -> _PreparationResult:
            return context.run(operation, *args, **kwargs)

        try:
            future = asyncio.get_running_loop().run_in_executor(None, prepare)
        except BaseException:
            self._preparation_slots.release()
            raise
        self._preparation_jobs.add(future)

        def finished(done: asyncio.Future[_PreparationResult]) -> None:
            self._preparation_jobs.discard(done)
            self._preparation_slots.release()
            if not done.cancelled():
                done.exception()

        future.add_done_callback(finished)
        # The caller can stop immediately; its worker holds the slot until it exits.
        return await asyncio.shield(future)
