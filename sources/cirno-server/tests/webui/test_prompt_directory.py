"""Navigation reads bounded metadata pages and searches without loading chat bodies."""

import json
import time

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.webui.services import build_server_services
from websockets.datastructures import Headers
from websockets.http11 import Request


async def directory(history, tmp_path):
    server = build_server_services(
        config=WebSocketConfig(), bus=MessageBus(), session_manager=history.sessions,
        static_dist_path=None, workspace_path=tmp_path, config_path=tmp_path / "config.json",
        default_restrict_to_workspace=False, runtime_model_name=None,
    )
    server.tokens.api_tokens["token"] = time.monotonic() + 60
    path = "/v0/sessions/websocket%3Adirectory/webui-thread/prompts"

    async def read(query="", etag=None):
        headers = Headers([("Authorization", "Bearer token")])
        if etag:
            headers["If-None-Match"] = etag
        return await server.http.sessions_routes._dispatch_session_routes(Request(path + query, headers), path)
    return read


async def test_directory_pages_search_and_validators_keep_global_positions(history, tmp_path):
    key = "websocket:directory"
    for index in range(513):
        history.append(key, {"event": "user", "text": ("NEEDLE " if index in (1, 500) else "") + str(index), "turn_id": f"t{index}"})
        history.append(key, {"event": "message", "text": "answer " + "x" * 1000, "turn_id": f"t{index}"})
        history.append(key, {"event": "turn_end", "turn_id": f"t{index}"})
    read = await directory(history, tmp_path)
    latest = await read()
    body = json.loads(latest.body)
    assert body["count"] == body["total"] == 513
    assert body["offset"] == 449 and len(body["prompts"]) == 64
    assert [prompt["index"] for prompt in body["prompts"]] == list(range(449, 513))
    assert len(latest.body) < 64 * 1100
    unchanged = await read(etag=latest.headers["ETag"])
    assert unchanged.status_code == 304
    # A validator for the latest page cannot validate an older page or a search.
    first = await read("?offset=0&limit=1", etag=latest.headers["ETag"])
    assert first.status_code == 200 and json.loads(first.body)["prompts"][0]["index"] == 0
    search = await read("?q=needle&offset=0&limit=1", etag=latest.headers["ETag"])
    found = json.loads(search.body)
    assert found["count"] == 513 and found["total"] == 2
    assert found["prompts"][0]["index"] == 1
    next_page = json.loads((await read("?q=needle&offset=1&limit=1")).body)
    assert next_page["prompts"][0]["index"] == 500
    cursor = next_page["prompts"][0]["cursor"]
    replay = history.build(key, after=cursor, limit=1)
    assert replay["events"][0]["projection_id"] == next_page["prompts"][0]["id"]
    assert json.loads((await read("?offset=9000")).body)["prompts"] == []


@pytest.mark.parametrize("query", ["?offset=-1", "?offset=", "?offset=x", "?offset=9007199254740992", "?limit=0", "?limit=257", "?limit="])
async def test_invalid_page_inputs_are_rejected_before_reading_history(history, tmp_path, query, monkeypatch):
    read = await directory(history, tmp_path)
    monkeypatch.setattr("cirno_core.session.transcript.prompt_directory_page", lambda *a, **kw: pytest.fail("invalid query reached storage"))
    assert (await read(query)).status_code == 400


async def test_directory_controls_are_filtered_and_corrupt_projection_errors_propagate(history, tmp_path, monkeypatch):
    for index, text in enumerate(("first", "/model DeepSeek", "hidden", "last")):
        history.append("websocket:directory", {"event": "user", "text": text, "turn_id": "webui-system:1" if index == 2 else f"t{index}"})
    read = await directory(history, tmp_path)
    body = json.loads((await read()).body)
    assert body["total"] == 2
    assert [row["preview"] for row in body["prompts"]] == ["first", "last"]
    assert [row["index"] for row in body["prompts"]] == [0, 1]

    def broken(*args, **kwargs):
        raise ValueError("corrupt stored projection")
    monkeypatch.setattr("cirno_core.session.transcript.prompt_directory_page", broken)
    with pytest.raises(ValueError, match="corrupt stored projection"):
        await read()
