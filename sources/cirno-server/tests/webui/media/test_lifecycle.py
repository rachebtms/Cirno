"""Cancellation, disconnect and I/O failures retain and release the actual file."""

import asyncio
from contextlib import contextmanager
from threading import Event

import pytest
from aiohttp import ClientPayloadError
from aiohttp.test_utils import make_mocked_request
from cirno_core.security.workspace_access import default_workspace_scope
from cirno_server.webui.media import http
from cirno_server.webui.media.http import MediaHTTP


async def test_cancel_during_open_waits_then_closes_snapshot(tmp_path, media_client, monkeypatch):
    gateway, _ = media_client
    source = tmp_path / "file.txt"
    source.write_bytes(b"data")
    url = gateway.sign_or_stage_media_path(source)["url"]
    entered, release, closed = Event(), Event(), Event()
    real_open = http.open_atomic_snapshot

    @contextmanager
    def slow_open(path):
        with real_open(path) as stream:
            entered.set()
            assert release.wait(3)
            try:
                yield stream
            finally:
                closed.set()

    monkeypatch.setattr(http, "open_atomic_snapshot", slow_open)
    handler = MediaHTTP(gateway, lambda _: default_workspace_scope(tmp_path, True))
    task = asyncio.create_task(handler.handle(make_mocked_request("GET", url)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not closed.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert closed.is_set()


async def test_atomic_replacement_does_not_mix_download_versions(
    tmp_path, media_client, monkeypatch
):
    gateway, client = media_client
    source = tmp_path / "original.pdf"
    original = b"A" * (1024 * 1024)
    source.write_bytes(original)
    url = gateway.sign_or_stage_media_path(source)["url"]
    entered, release = Event(), Event()
    real_open = http.open_atomic_snapshot

    class Reader:
        reads = 0

        def __init__(self, stream):
            self.stream = stream

        def fileno(self):
            return self.stream.fileno()

        def seek(self, *args):
            return self.stream.seek(*args)

        def read(self, size):
            self.reads += 1
            if self.reads == 2:
                entered.set()
                assert release.wait(3)
            return self.stream.read(size)

    @contextmanager
    def snapshot(path):
        with real_open(path) as stream:
            yield Reader(stream)

    monkeypatch.setattr(http, "open_atomic_snapshot", snapshot)
    try:
        async with client.get(url) as response:
            first = await response.content.readexactly(http.MEDIA_CHUNK_BYTES)
            assert await asyncio.to_thread(entered.wait, 2)
            replacement = source.with_suffix(".next")
            replacement.write_bytes(b"B" * len(original))
            replacement.replace(source)
            release.set()
            assert first + await response.read() == original
    finally:
        release.set()
    assert source.read_bytes() == b"B" * len(original)


async def test_read_error_aborts_download_and_releases_file(
    tmp_path, media_client, monkeypatch, caplog
):
    gateway, client = media_client
    source = tmp_path / "results.pdf"
    source.write_bytes(b"x" * (128 * 1024))
    url = gateway.sign_or_stage_media_path(source)["url"]
    real_open = http.open_atomic_snapshot
    closed = Event()

    class FaultyReader:
        reads = 0

        def __init__(self, stream):
            self.stream = stream

        def fileno(self):
            return self.stream.fileno()

        def seek(self, *args):
            return self.stream.seek(*args)

        def read(self, size):
            self.reads += 1
            if self.reads == 2:
                raise OSError("Injected media disk read failure")
            return self.stream.read(size)

    @contextmanager
    def snapshot(path):
        with real_open(path) as stream:
            try:
                yield FaultyReader(stream)
            finally:
                closed.set()

    monkeypatch.setattr(http, "open_atomic_snapshot", snapshot)
    async with client.get(url) as response:
        with pytest.raises(ClientPayloadError):
            await response.read()
    assert closed.is_set()
    assert "Injected media disk read failure" in caplog.text


async def test_disconnect_closes_snapshot_after_accepted_read_settles(
    tmp_path, media_client, monkeypatch
):
    gateway, client = media_client
    source = tmp_path / "disconnect.pdf"
    with source.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024)
    url = gateway.sign_or_stage_media_path(source)["url"]
    real_open = http.open_atomic_snapshot
    entered, release, closed = Event(), Event(), Event()

    class Reader:
        reads = 0

        def __init__(self, stream):
            self.stream = stream

        def fileno(self):
            return self.stream.fileno()

        def seek(self, *args):
            return self.stream.seek(*args)

        def read(self, size):
            self.reads += 1
            if self.reads == 2:
                entered.set()
                assert release.wait(3)
            return self.stream.read(size)

    @contextmanager
    def snapshot(path):
        with real_open(path) as stream:
            try:
                yield Reader(stream)
            finally:
                closed.set()

    monkeypatch.setattr(http, "open_atomic_snapshot", snapshot)
    try:
        response = await client.get(url)
        await response.content.readexactly(http.MEDIA_CHUNK_BYTES)
        assert await asyncio.to_thread(entered.wait, 2)
        response.close()
        assert not closed.is_set()
        release.set()
        assert await asyncio.to_thread(closed.wait, 2)
    finally:
        release.set()


async def test_session_authority_stays_on_the_http_event_loop(tmp_path, media_client, monkeypatch):
    gateway, client = media_client
    source = tmp_path / "scoped.pdf"
    source.write_bytes(b"research")
    url = gateway.local_attachment_url(str(source), session_key="websocket:research")
    owner = asyncio.get_running_loop()
    authorize = gateway.authorize_media_reference
    calls = []

    def require_owner(*args, **kwargs):
        assert asyncio.get_running_loop() is owner
        calls.append(True)
        return authorize(*args, **kwargs)

    monkeypatch.setattr(gateway, "authorize_media_reference", require_owner)
    async with client.get(url) as response:
        assert response.status == 200
        assert await response.read() == b"research"
    assert calls == [True]
