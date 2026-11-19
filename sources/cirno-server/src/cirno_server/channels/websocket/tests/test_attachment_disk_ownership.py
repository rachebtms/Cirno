"""Tiny simulated disk stalls must not block or outlive their upload owner."""

import asyncio
import os
import threading
import time
from pathlib import Path

import pytest

from cirno_server.channels.websocket.attachment_store import AttachmentStore


async def body():
    yield b"tiny"


def instrument_output(monkeypatch, root, phase, gate):
    opened = Path.open

    class Output:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def write(self, chunk):
            if phase == "write":
                gate()
            return self.stream.write(chunk)

        def __exit__(self, *exception):
            try:
                if phase == "close":
                    gate()
            finally:
                self.stream.close()

    def open_output(path, mode="r", *args, **kwargs):
        if mode == "xb" and path.is_relative_to(root):
            if phase == "open":
                gate()
            return Output(opened(path, mode, *args, **kwargs))
        return opened(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_output)


@pytest.mark.parametrize("phase", ["open", "write", "close"])
async def test_slow_output_keeps_the_event_loop_responsive(tmp_path, monkeypatch, phase):
    loop, release = asyncio.get_running_loop(), threading.Event()

    def disk_step():
        loop.call_soon_threadsafe(release.set)
        if not release.wait(.2):
            raise RuntimeError("Event loop blocked by upload disk I/O")

    instrument_output(monkeypatch, tmp_path, phase, disk_step)
    store = AttachmentStore(tmp_path)
    ref = await store.upload(body(), owner="owner", mime="image/png", size=4)
    assert Path(store.commit([ref], owner="owner")[0]).read_bytes() == b"tiny"


async def test_prune_does_not_delete_an_upload_that_still_owns_its_writer(tmp_path):
    store = AttachmentStore(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()

    async def stalled_body():
        yield b"t"
        entered.set()
        await release.wait()
        yield b"iny"

    task = asyncio.create_task(store.upload(stalled_body(), owner="owner", mime="image/png", size=4))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        marker, = store._journal.iterdir()
        old = time.time() - store.ttl_seconds - store.upload_timeout - 1
        os.utime(marker, (old, old))
        store.prune()
        assert (tmp_path / marker.name).is_file()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    ref = task.result()
    assert Path(store.commit([ref], owner="owner")[0]).read_bytes() == b"tiny"


@pytest.mark.parametrize("phase", ["open", "write", "close"])
async def test_repeated_cancellation_retains_writer_and_capacity_until_disk_settles(tmp_path, monkeypatch, phase):
    entered, release = threading.Event(), threading.Event()
    once = False

    def disk_step():
        nonlocal once
        if once:
            return
        once = True
        entered.set()
        if not release.wait(1):
            raise RuntimeError("Fixture disk was not released")

    instrument_output(monkeypatch, tmp_path, phase, disk_step)
    store = AttachmentStore(tmp_path, max_pending=1, max_pending_bytes=4)
    task = asyncio.create_task(store.upload(body(), owner="owner", mime="image/png", size=4))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert store._active == 1 and store._reserved_bytes == 4
            assert len(store._active_paths) == 1
    finally:
        release.set()
        result, = await asyncio.gather(task, return_exceptions=True)
    assert isinstance(result, asyncio.CancelledError)
    assert store._active == store._reserved_bytes == 0 and not store._active_paths
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    ref = await store.upload(body(), owner="owner", mime="image/png", size=4)
    assert Path(store.commit([ref], owner="owner")[0]).read_bytes() == b"tiny"


@pytest.mark.parametrize("phase", ["open", "write", "close"])
async def test_total_deadline_covers_disk_io_and_waits_for_safe_cleanup(tmp_path, monkeypatch, phase):
    entered, release = threading.Event(), threading.Event()
    original_timeout = asyncio.timeout
    deadline = original_timeout(None)
    store = AttachmentStore(tmp_path, upload_timeout=17)

    def timeout(seconds):
        return deadline if seconds == 17 else original_timeout(seconds)

    def disk_step():
        entered.set()
        if not release.wait(1):
            raise RuntimeError("Fixture disk was not released")

    monkeypatch.setattr("cirno_server.channels.websocket.attachment_store.asyncio.timeout", timeout)
    instrument_output(monkeypatch, tmp_path, phase, disk_step)
    task = asyncio.create_task(store.upload(body(), owner="owner", mime="image/png", size=4))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        deadline.reschedule(asyncio.get_running_loop().time() - 1)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        assert store._active == 1 and store._reserved_bytes == 4
    finally:
        release.set()
        result, = await asyncio.gather(task, return_exceptions=True)
    assert isinstance(result, TimeoutError)
    assert store._active == store._reserved_bytes == 0 and not store._active_paths
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.parametrize("phase", ["write", "close"])
async def test_disk_failure_cleans_the_owned_file_and_capacity(tmp_path, monkeypatch, phase):
    def failed():
        raise OSError("Fixture disk failed")

    instrument_output(monkeypatch, tmp_path, phase, failed)
    store = AttachmentStore(tmp_path)
    with pytest.raises(OSError, match="Fixture disk failed"):
        await store.upload(body(), owner="owner", mime="image/png", size=4)
    assert not store._entries and not store._active_paths
    assert store._active == store._reserved_bytes == 0
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


async def test_a_colliding_upload_cannot_release_the_first_uploads_file_lease(tmp_path, monkeypatch):
    path = tmp_path / "fixed.png"
    monkeypatch.setattr("cirno_server.channels.websocket.attachment_store.media_destination", lambda *args, **kwargs: path)
    store = AttachmentStore(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()

    async def stalled_body():
        yield b"t"
        entered.set()
        await release.wait()
        yield b"iny"

    first = asyncio.create_task(store.upload(stalled_body(), owner="first", mime="image/png", size=4))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(FileExistsError):
            await store.upload(body(), owner="second", mime="image/png", size=4)
        marker = store._journal / path.name
        old = time.time() - store.ttl_seconds - store.upload_timeout - 1
        os.utime(marker, (old, old))
        store.prune()
        assert path.is_file()
        assert store._active == 1 and store._reserved_bytes == 4
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)
    assert Path(store.commit([first.result()], owner="first")[0]).read_bytes() == b"tiny"
