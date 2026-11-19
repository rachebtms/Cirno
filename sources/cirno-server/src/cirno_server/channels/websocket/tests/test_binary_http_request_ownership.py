"""HTTP shutdown retains accepted file I/O without opening a network listener."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from cirno_server.channels.websocket import binary_http
from cirno_server.channels.websocket.attachment_store import AttachmentStore


class HTTPServer:
    def __init__(self, handler, **options):
        self.request_handler = handler
        self.stopping = asyncio.Event()

    async def shutdown(self, *, timeout):
        self.stopping.set()


@pytest.mark.parametrize("cancel_shutdown", [False, True])
async def test_shutdown_waits_for_accepted_upload_disk_cleanup(tmp_path, monkeypatch, cancel_shutdown):
    monkeypatch.setattr(binary_http.web, "Server", HTTPServer)
    entered, release = threading.Event(), threading.Event()
    opened = Path.open

    def delayed_open(path, mode="r", *args, **kwargs):
        if mode == "xb":
            entered.set()
            if not release.wait(1):
                raise RuntimeError("Fixture upload open was not released")
        return opened(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", delayed_open)
    store = AttachmentStore(tmp_path)

    async def body():
        yield b"tiny"

    async def upload(request):
        return await store.upload(body(), owner="owner", mime="image/png", size=4)

    bridge = binary_http.BinaryHTTPBridge(upload)
    request = asyncio.create_task(bridge.http_server.request_handler(SimpleNamespace(transport=None)))
    shutdown = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        shutdown = asyncio.create_task(bridge.shutdown())
        await bridge.http_server.stopping.wait()
        if cancel_shutdown:
            shutdown.cancel()
            await asyncio.sleep(0)
            shutdown.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not shutdown.done()
        assert store._active == 1 and store._reserved_bytes == 4
    finally:
        release.set()
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        result = None if shutdown is None else (await asyncio.gather(shutdown, return_exceptions=True))[0]
    assert isinstance(result, asyncio.CancelledError) if cancel_shutdown else result is None
    store.clear()
    assert not store._active and not store._active_paths and not store._reserved_bytes
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.parametrize("failure", [False, True])
async def test_completed_http_handlers_release_their_request_lease(monkeypatch, failure):
    monkeypatch.setattr(binary_http.web, "Server", HTTPServer)

    async def handle(request):
        if failure:
            raise ValueError("Fixture handler failed")
        return "complete"

    bridge = binary_http.BinaryHTTPBridge(handle)
    if failure:
        with pytest.raises(ValueError, match="Fixture handler failed"):
            await bridge.http_server.request_handler(SimpleNamespace(transport=None))
    else:
        assert await bridge.http_server.request_handler(SimpleNamespace(transport=None)) == "complete"
    assert not bridge._requests
    await bridge.shutdown()
