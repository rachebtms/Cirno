"""Streaming GET routing must survive arbitrary request-line segmentation."""

import asyncio

import pytest
from aiohttp import web
from cirno_server.channels.websocket.binary_http import BinaryHTTPBridge
from websockets.asyncio.server import serve


@pytest.mark.parametrize("path", ["/v0/media/sig/payload", "/v0/backups/download?ticket=test"])
async def test_fragmented_streaming_get_uses_body_capable_http(path):
    received = []

    async def stream(request):
        received.append((request.method, request.path, request.remote))
        response = web.StreamResponse(headers={"Content-Length": "6"})
        response.force_close()
        await response.prepare(request)
        await response.write(b"abc")
        await response.write(b"def")
        await response.write_eof()
        return response

    async def websocket(connection):
        pytest.fail("A signed download must not start a WebSocket handshake")

    bridge = BinaryHTTPBridge(stream)
    server = await serve(websocket, "127.0.0.1", 0, create_connection=bridge.connection_factory)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        for (
            value
        ) in f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode():
            writer.write(bytes([value]))
            await writer.drain()
            await asyncio.sleep(0)
        response = await asyncio.wait_for(reader.read(), 2)
        assert b"200 OK" in response and response.endswith(b"abcdef")
        assert received == [("GET", path.split("?")[0], "127.0.0.1")]
    finally:
        writer.close()
        await writer.wait_closed()
        server.close()
        await bridge.shutdown()
        await server.wait_closed()
