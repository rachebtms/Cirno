"""Cancelling image preparation keeps its accepted worker attached."""

import asyncio
from threading import Event

import pytest
from cirno_core.providers import images


@pytest.mark.parametrize("outcome", ["ok", "error"])
async def test_image_copy_worker_settles_before_cancellation_returns(monkeypatch, outcome):
    entered, release, settled = Event(), Event(), Event()
    body = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]}]}

    def prepare(value, _size):
        assert value is body
        entered.set()
        try:
            assert release.wait(2)
            if outcome == "error":
                raise ValueError("fake image preparation failed after cancellation")
            return value
        finally:
            settled.set()

    monkeypatch.setattr(images, "INLINE_IMAGE_BYTE_BUDGET", 0)
    monkeypatch.setattr(images, "_prepare_copies", prepare)
    task = asyncio.create_task(images.prepare_inline_images(body))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(settled.wait, 1)
    assert task.cancelled()


async def test_small_image_request_keeps_identity_without_starting_copy_worker(monkeypatch):
    def unexpected(*_args):
        pytest.fail("Small requests must not start an image worker")

    body = {"messages": [{"role": "user", "content": "Just text"}]}
    monkeypatch.setattr(images, "_prepare_copies", unexpected)
    assert await images.prepare_inline_images(body) is body
