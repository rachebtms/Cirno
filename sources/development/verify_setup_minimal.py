"""Verify minimal image behavior with a local fake provider and no extra installs."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import websockets


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/v1/chat/completions", self.path
        tools = {tool["function"]["name"] for tool in request.get("tools", [])}
        router = "user__message" in tools
        reply = {"role": "assistant", "content": "minimal-llm-ok"}
        finish = "stop"
        if router and request["messages"][-1]["role"] != "tool":
            reply = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_minimal", "type": "function", "function": {
                    "name": "user__message", "arguments": json.dumps({"content": "minimal-router-ok"}),
                },
            }]}
            finish = "tool_calls"
        elif router:
            reply = {"role": "assistant", "content": ""}
        envelope = {"id": "chatcmpl-minimal", "model": "minimal-probe", "created": int(time.time())}
        if request.get("stream"):
            delta = dict(reply)
            if "tool_calls" in delta:
                delta["tool_calls"] = [{"index": 0, **delta["tool_calls"][0]}]
            packets = [
                {**envelope, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {**envelope, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
            ]
            content = "".join("data: " + json.dumps(packet) + "\n\n" for packet in packets) + "data: [DONE]\n\n"
            mime = "text/event-stream"
        else:
            content = json.dumps({**envelope, "object": "chat.completion", "choices": [{"index": 0, "message": reply, "finish_reason": finish}]})
            mime = "application/json"
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


async def receive(socket, event):
    async with asyncio.timeout(60):
        while True:
            frame = json.loads(await socket.recv())
            if frame.get("event") == event:
                return frame


async def turn(socket, chat_id, content, marker, *, shell=False):
    await socket.send(json.dumps({"type": "message", "chat_id": chat_id, "content": content,
                                  "webui": True, "user_shell": shell, "turn_id": marker}))
    frames = []
    async with asyncio.timeout(60):
        while True:
            frame = json.loads(await socket.recv())
            frames.append(frame)
            if frame.get("event") == "turn_end" and frame.get("turn_id") == marker:
                break
    assert marker in json.dumps(frames), frames
    assert not any(frame.get("event") == "error" for frame in frames), frames
    # The turn id also contains the marker, so require it in actual reply text.
    assert any(marker in str(frame.get("text", "")) or marker in str(frame.get("delta", "")) for frame in frames), frames


async def verify(provider_port):
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8765", trust_env=False, timeout=30) as browser:
        assert (await browser.get("/")).status_code == 200
        status = (await browser.get("/v0/auth/status")).json()
        action = "register" if status["registration_required"] else "login"
        result = await browser.post(f"/v0/auth/{action}", json={"username": "ci-owner", "password": "Ci-container-smoke-password!"})
        assert result.status_code in {200, 201}, result.text
        assert (await browser.post("/v0/auth/complete", json={"wake": False})).is_success
        bootstrap = (await browser.get("/v0/bootstrap")).json()
        browser.headers["Authorization"] = f'Bearer {bootstrap["api_token"]}'
        settings_response = await browser.get("/v0/settings")
        settings_response.raise_for_status()
        settings = settings_response.json()
        assert not any(path.startswith("tools.startup.") for path in settings["runtime_config"])
        assert "setup_components" not in settings["runtime"]
        async with websockets.connect(f'{bootstrap["ws_url"]}?token={bootstrap["token"]}&client_id=minimal-smoke') as socket:
            await receive(socket, "ready")
            await socket.send(json.dumps({"type": "webui_request", "request_id": "provider", "action": "settings.provider.create", "payload": {
                "name": "Minimal smoke provider", "api_key": "local-fixture-only",
                "api_base": f"http://127.0.0.1:{provider_port}/v1",
            }}))
            result = await receive(socket, "webui_response")
            assert result["ok"], result
            provider = result["result"]["created_provider"]
            await socket.send(json.dumps({"type": "webui_request", "request_id": "model", "action": "settings.model_configuration.create", "payload": {
                "name": "Minimal smoke model", "provider": provider, "model": "minimal-probe",
                "max_tokens": 2048, "context_window_tokens": 128000,
            }}))
            result = await receive(socket, "webui_response")
            assert result["ok"], result
            await socket.send(json.dumps({"type": "new_chat"}))
            chat = (await receive(socket, "attached"))["chat_id"]
            await turn(socket, chat, "Reply briefly to this local test", "minimal-llm-ok")
            await turn(socket, chat, "!printf minimal-file-ok > minimal-probe.txt; cat minimal-probe.txt", "minimal-file-ok", shell=True)
            from cirno_core.session.keys import ROUTER_CHAT_ID

            await socket.send(json.dumps({"type": "attach", "chat_id": ROUTER_CHAT_ID}))
            await receive(socket, "attached")
            await turn(socket, ROUTER_CHAT_ID, "Send a brief reply", "minimal-router-ok")
        settings = (await browser.get("/v0/settings")).json()
        assert settings["model_presets"]
        assert not any(path.startswith("tools.startup.") for path in settings["runtime_config"])
    from cirno_memory.repository import MemoryRepository

    with tempfile.TemporaryDirectory() as temporary:
        repository = MemoryRepository(Path(temporary))
        record = repository.save("Minimal keyword memory evidence", source="smoke", session_key="unit")
        assert repository.search("keyword memory", session_key="unit")["memories"][0]["id"] == record["id"]
    print("OK minimal registration/settings, configured provider, Worker reply, Router reply tool, shell/file IO and keyword memory", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        asyncio.run(verify(server.server_port))
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
