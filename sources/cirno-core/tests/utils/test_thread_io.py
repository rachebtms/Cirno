"""A storage owner keeps its lock until admitted physical I/O has settled."""

import asyncio
import threading

import pytest

from cirno_core.utils.thread_io import SerializedThreadIO


@pytest.mark.parametrize("fails", [False, True])
async def test_repeated_cancel_drains_the_writer_before_admitting_its_successor(fails):
    io = SerializedThreadIO()
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    events = []

    def write(value, *, suffix):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(2)
        events.append(value + suffix)
        if fails:
            raise OSError("writer failed after cancellation")
        return "receipt"

    first = asyncio.create_task(io(write, "saved", suffix="!"))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        first.cancel()
        await asyncio.sleep(0)
        first.cancel()
        second = asyncio.create_task(io(lambda: events.append("next")))
        await asyncio.sleep(0)
        assert not first.done()
        assert events == []
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
    assert first.cancelled()
    assert events == ["saved!", "next"]


async def test_cancelled_waiter_does_not_start_physical_work():
    io = SerializedThreadIO()
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    events = []

    def write():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(2)

    first = asyncio.create_task(io(write))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        queued = asyncio.create_task(io(lambda: events.append("unexpected")))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
    finally:
        release.set()
        await first
    assert events == []


async def test_error_releases_the_owner_and_preserves_successful_results():
    io = SerializedThreadIO()

    def fail():
        raise OSError("write rejected")

    with pytest.raises(OSError, match="write rejected"):
        await io(fail)
    assert await io(lambda: "receipt") == "receipt"
