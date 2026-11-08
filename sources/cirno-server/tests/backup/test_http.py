"""Exercise authenticated transfer and streaming downloads on the shared listener."""

from types import SimpleNamespace

import httpx
import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.backup.http import BackupHTTP
from cirno_server.channels.websocket.binary_http import BinaryHTTPBridge
from websockets.asyncio.server import serve


async def test_shared_listener_streams_full_backup_and_requires_capability(tmp_path):
    save_config(Config(), tmp_path / "config.json")
    service = BackupHTTP(
        tmp_path / "config.json",
        SimpleNamespace(authorized=lambda token: token == "owner"),
        MessageBus(),
        None,
    )
    bridge = BinaryHTTPBridge(service.handle)

    async def unused(connection):
        pytest.fail("Backup HTTP requests must not enter WebSocket dispatch")

    async with serve(unused, "127.0.0.1", 0, create_connection=bridge.connection_factory) as server:
        base = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        async with httpx.AsyncClient(base_url=base) as client:
            denied = await client.post("/v0/backups/export", json={"paths": []})
            assert denied.status_code == 401
            with service.bus.admission.activity():
                busy = await client.post(
                    "/v0/backups/export",
                    headers={"Authorization": "Bearer owner"},
                    json={"paths": []},
                )
                assert busy.status_code == 409
                assert not service.bus.admission.paused
            response = await client.post(
                "/v0/backups/export", headers={"Authorization": "Bearer owner"}, json={"paths": []}
            )
            assert response.status_code == 200, response.text
            url = response.json()["url"]
            download = await client.get(url)
            assert download.status_code == 200
            assert download.headers["content-disposition"].startswith("attachment;")
            assert download.content[:2] == b"\x1f\x8b"
            assert int(download.headers["content-length"]) == len(download.content)
            # Browser range requests can resume without loading the archive into RAM.
            part = await client.get(url, headers={"Range": "bytes=0-9"})
            assert part.status_code == 206 and part.content == download.content[:10]
            upload = await client.post(
                "/v0/backups/upload",
                content=download.content,
                headers={"Authorization": "Bearer owner"},
            )
            assert upload.status_code == 200, upload.text
            assert upload.json()["format"] == "cirno-instance-backup"
            service.uploads.authorized = lambda _: False
            assert (await client.get(url)).status_code == 401
        await bridge.shutdown()


async def test_cancelling_a_preview_preserves_another_pending_restore(tmp_path):
    import json
    import shutil

    save_config(Config(), tmp_path / "config.json")
    service = BackupHTTP(tmp_path / "config.json", SimpleNamespace(authorized=lambda _: True), MessageBus(), None)
    archive, _ = service.archive.create([])
    previews = []
    for index in range(2):
        uploaded = tmp_path / f"upload-{index}.gz"
        shutil.copy2(archive, uploaded)
        previews.append(service.archive.inspect(uploaded))
    service.archive.prepare_restore(previews[0]["id"], {})

    class Body:
        async def iter_chunked(self, size):
            yield json.dumps({"id": previews[1]["id"]}).encode()

    request = SimpleNamespace(method="POST", path="/v0/backups/cancel", headers={"Authorization": "Bearer owner"}, content=Body())
    assert (await service.handle(request)).status == 200
    plan = json.loads((service.archive.store / "restore-plan.json").read_text())
    assert plan["id"] == previews[0]["id"]
    assert service.archive.apply_pending()
