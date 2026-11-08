"""Settle temporary request evidence before propagating execution cancellation."""

import asyncio

from cirno_core.utils.cancellation import shield_and_drain


async def begin_request(recordings, *args):
    operation = asyncio.create_task(asyncio.to_thread(recordings.begin, *args))
    try:
        return await shield_and_drain(operation)
    except asyncio.CancelledError:
        handles = operation.result()
        await end_request(recordings, handles, {"error": "CancelledError"}, "cancelled")
        raise


async def end_request(recordings, handles, response, status):
    await shield_and_drain(asyncio.to_thread(recordings.finish, handles, response, status))
