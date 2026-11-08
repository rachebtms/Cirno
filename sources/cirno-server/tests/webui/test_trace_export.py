"""Export a complete snapshot without losing long-context request data."""
import io
import json
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cirno_core.observability.recordings import TraceRecordings
from cirno_core.session.display_history import HistoryFact, HistoryKind
from cirno_server.webui.trace_http import TraceHTTP


def test_zip_contains_every_event_and_deduplicated_complete_requests_even_after_close(tmp_path, monkeypatch):
    recordings = TraceRecordings()
    identifier = str(uuid4())
    info = recordings.create(identifier)
    prefix = {"role": "system", "content": "共享上下文 " * 10000}
    tools = [{"name": "nodes.execute"}]
    for i in range(150):
        recordings.facts("websocket:worker", [HistoryFact(HistoryKind.INPUT, {"text": f"event {i}"}, "turn")])
    for i in range(2):
        handles = recordings.begin("websocket:router", "model", [prefix, {"role": "user", "content": str(i)}], tools)
        recordings.finish(handles, {"content": f"response {i}"}, "completed")
    from cirno_core.observability import recording_export
    write = recording_export.write_recording_zip
    def close_before_compression(*args):
        recordings.close_all()
        write(*args)
    monkeypatch.setattr(recording_export, "write_recording_zip", close_before_compression)
    output = tmp_path / "trace.zip"
    recordings.export(identifier, info["epoch"], output)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        events = [json.loads(line) for line in archive.read("events.jsonl").splitlines()]
        requests = [json.loads(line) for line in archive.read("requests.jsonl").splitlines()]
        assert manifest["count"] == len(events) == 152  # Entire recording, beyond the 100-event page.
        assert events[0]["body"]["content"]["text"] == "event 0"
        assert requests[0]["inputs"][0] == requests[1]["inputs"][0]
        for index, request in enumerate(requests):
            blob = lambda digest: json.loads(archive.read(f"blobs/{digest}.json"))
            assert [blob(d) for d in request["inputs"]] == [prefix, {"role": "user", "content": str(index)}]
            assert blob(request["tools"]) == tools
            assert blob(request["response"]) == {"content": f"response {index}"}
    assert not recordings.active


async def test_export_http_requires_live_capability_and_preserves_epoch(tmp_path, monkeypatch):
    recordings = TraceRecordings()
    identifier = str(uuid4())
    info = recordings.create(identifier)
    monkeypatch.setattr("cirno_server.webui.trace_http.current_recordings", lambda: recordings)
    handler = TraceHTTP(SimpleNamespace(authorized=lambda token: token == "live-owner"))
    app = web.Application()
    app.router.add_post("/v0/traces/export", handler.handle)
    try:
        async with TestClient(TestServer(app)) as client:
            values = {"recording_id": identifier, "epoch": info["epoch"]}
            assert (await client.post("/v0/traces/export", json=values)).status == 401
            headers = {"Authorization": "Bearer live-owner"}
            response = await client.post("/v0/traces/export", json=values, headers=headers)
            assert response.status == 200 and response.content_type == "application/zip"
            assert response.headers["Cache-Control"] == "no-store"
            with ZipFile(io.BytesIO(await response.read())) as archive:
                assert json.loads(archive.read("manifest.json"))["count"] == 0
            recordings.operation(identifier, "clear", {})
            stale = await client.post("/v0/traces/export", json=values, headers=headers)
            assert stale.status == 400 and "cleared" in (await stale.json())["error"]
            missing = await client.post("/v0/traces/export", json={**values, "recording_id": str(uuid4())}, headers=headers)
            assert missing.status == 404
    finally:
        recordings.close_all()
