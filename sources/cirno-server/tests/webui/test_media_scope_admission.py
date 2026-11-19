"""Signed media scope revalidation, using tiny files and an in-memory HTTP writer."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest
from cirno_core.security.workspace_access import default_workspace_scope
from cirno_server.webui.media import http
from cirno_server.webui.media.resources import MediaReference
from cirno_server.webui.media_gateway import WebUIMediaServer


class MemoryResponse:
    def __init__(self, *, status, headers):
        self.status, self.headers, self.body = status, headers, bytearray()

    def force_close(self):
        pass

    async def prepare(self, request):
        pass

    async def write(self, chunk):
        self.body.extend(chunk)

    async def write_eof(self):
        pass


@pytest.mark.parametrize("phase", ["resolve", "open"])
@pytest.mark.parametrize("change", ["delete", "workspace"])
async def test_scope_change_during_media_io_cannot_publish_the_previous_scope(tmp_path, monkeypatch, phase, change):
    first, second, media = [tmp_path / name for name in ("first", "second", "media")]
    for folder in (first, second, media):
        folder.mkdir()
    file = first / "research.txt"
    file.write_bytes(b"Private research")
    scope = [default_workspace_scope(first, True)]
    replacement = None if change == "delete" else default_workspace_scope(second, True)
    loop, owner_thread = asyncio.get_running_loop(), threading.get_ident()

    def current_scope(key):
        assert key == "owner" and threading.get_ident() == owner_thread
        return scope[0]

    gateway = WebUIMediaServer(workspace_path=first, logger=Mock(), media_dir=lambda _: media)
    url = gateway.local_attachment_url(str(file), session_key="owner")
    request = SimpleNamespace(method="GET", path=urlsplit(url).path, headers={})
    handler = http.MediaHTTP(gateway, current_scope)
    resolve, opened = MediaReference.resolve, http.open_atomic_snapshot

    def delayed_resolve(reference):
        result = resolve(reference)
        if phase == "resolve":
            loop.call_soon_threadsafe(scope.__setitem__, 0, replacement)
        return result

    def delayed_open(path):
        result = opened(path)
        if phase == "open":
            loop.call_soon_threadsafe(scope.__setitem__, 0, replacement)
        return result

    monkeypatch.setattr(MediaReference, "resolve", delayed_resolve)
    monkeypatch.setattr(http, "open_atomic_snapshot", delayed_open)
    monkeypatch.setattr(http.web, "StreamResponse", MemoryResponse)
    response = await handler.handle(request)
    assert response.status == (404 if change == "delete" else 403)
    assert b"Private research" not in response.body


async def test_unchanged_scope_retains_range_and_head_transfer(tmp_path, monkeypatch):
    file = tmp_path / "sample.txt"
    file.write_bytes(b"Research")
    gateway = WebUIMediaServer(workspace_path=tmp_path, logger=Mock(), media_dir=lambda _: tmp_path)
    handler = http.MediaHTTP(gateway, lambda _: default_workspace_scope(tmp_path, True))
    path = urlsplit(gateway.local_attachment_url(str(file), session_key="owner")).path
    monkeypatch.setattr(http.web, "StreamResponse", MemoryResponse)
    response = await handler.handle(SimpleNamespace(method="GET", path=path, headers={"Range": "bytes=2-4"}))
    assert response.status == 206 and response.body == b"sea"
    assert response.headers["Content-Length"] == "3"
    response = await handler.handle(SimpleNamespace(method="HEAD", path=path, headers={}))
    assert response.status == 200 and not response.body
    assert response.headers["Content-Length"] == "8"
