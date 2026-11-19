"""An upload capability cannot outlive its live connection owner."""

import json
import weakref
from types import SimpleNamespace

import pytest

from cirno_server.channels.websocket.attachment_http import UPLOAD_PATH, AttachmentHTTP
from cirno_server.channels.websocket.attachment_store import AttachmentStore


class Connection:
    pass


def test_capability_expires_when_the_weak_connection_owner_disappears(tmp_path):
    gateway = AttachmentHTTP(AttachmentStore(tmp_path))
    connection = Connection()
    owner = weakref.ref(connection)
    token = gateway.issue(connection)["token"]
    assert gateway.authorized(token)
    del connection
    assert owner() is None
    assert not gateway.authorized(token)


def test_live_connections_remain_isolated_when_a_capability_is_reissued(tmp_path):
    gateway = AttachmentHTTP(AttachmentStore(tmp_path))
    first, second = Connection(), Connection()
    previous, other = [gateway.issue(connection)["token"] for connection in (first, second)]
    replacement = gateway.issue(first)["token"]
    assert not gateway.authorized(previous)
    assert gateway.authorized(replacement) and gateway.authorized(other)
    gateway.revoke(second)
    assert not gateway.authorized(other) and gateway.authorized(replacement)


@pytest.mark.parametrize("disconnect", ["before-body", "during-body"])
async def test_http_rejects_an_orphaned_capability_without_retaining_a_file(tmp_path, disconnect):
    gateway = AttachmentHTTP(AttachmentStore(tmp_path))
    connection = Connection()
    holder = [connection]
    token = gateway.issue(connection)["token"]
    del connection
    read = False
    if disconnect == "before-body":
        holder.clear()

    async def body():
        nonlocal read
        read = True
        yield b"tiny"
        holder.clear()

    response = await gateway.handle(SimpleNamespace(
        path=UPLOAD_PATH, method="POST", content_length=4,
        headers={"Authorization": "Bearer " + token, "Content-Type": "image/png"},
        content=SimpleNamespace(iter_chunked=lambda _: body()),
    ))
    assert response.status == (401 if disconnect == "before-body" else 400)
    assert read is (disconnect == "during-body")
    assert not gateway.authorized(token)
    assert not gateway.store._entries and gateway.store._reserved_bytes == 0
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert "error" in json.loads(response.body)
