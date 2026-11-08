"""Ownership of blocking Bedrock event streams across async cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any

from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger


def _next(iterator: Iterator[dict[str, Any]]) -> dict[str, Any] | None:
    return next(iterator, None)


async def _close(response: dict[str, Any]) -> None:
    stream = response.get("stream")
    if stream is not None and (close := getattr(stream, "close", None)) is not None:
        await asyncio.to_thread(close)


async def _close_after_open(opening: asyncio.Task[dict[str, Any]]) -> None:
    try:
        response = await opening
    except Exception as error:
        logger.debug("Cancelled Bedrock stream request settled with {}", type(error).__name__)
    else:
        await _close(response)


@asynccontextmanager
async def stream_events(
    request: Callable[[], dict[str, Any]],
    *,
    idle_timeout_s: float,
) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
    """Close the response and settle outstanding SDK reads before releasing it."""
    opening = asyncio.create_task(asyncio.to_thread(request))
    try:
        response = await asyncio.shield(opening)
    except asyncio.CancelledError:
        await shield_and_drain(_close_after_open(opening))
        raise
    reading: asyncio.Task[dict[str, Any] | None] | None = None

    async def events() -> AsyncIterator[dict[str, Any]]:
        nonlocal reading
        iterator = iter(response.get("stream") or [])
        while True:
            reading = asyncio.create_task(asyncio.to_thread(_next, iterator))
            event = await asyncio.wait_for(asyncio.shield(reading), timeout=idle_timeout_s)
            reading = None
            if event is None:
                return
            yield event

    async def settle() -> None:
        try:
            await _close(response)
        finally:
            if reading is not None:
                results = await asyncio.gather(reading, return_exceptions=True)
                if isinstance(results[0], Exception):
                    logger.debug(
                        "Closed Bedrock stream read settled with {}", type(results[0]).__name__
                    )

    try:
        yield events()
    finally:
        await shield_and_drain(settle())
