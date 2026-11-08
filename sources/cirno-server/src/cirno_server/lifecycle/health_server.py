"""Bounded HTTP listener for readiness and the current runtime identity."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict

from cirno_core.runtime.admission import RuntimeAdmission

from cirno_server.api import HEALTH_PATH
from cirno_server.lifecycle.contracts import ServerHealthIdentity
from cirno_server.lifecycle.health import ChannelHealthSource, channel_readiness

MAX_CONNECTIONS = 64
READ_TIMEOUT_SECONDS = 2.0


class HealthListener:
    def __init__(
        self,
        channels: ChannelHealthSource,
        admission: RuntimeAdmission,
        identity: ServerHealthIdentity,
        *,
        on_listening: Callable[[str, int], None],
    ):
        self.channels, self.admission, self.identity = channels, admission, identity
        self.on_listening = on_listening
        self.connections = asyncio.Semaphore(MAX_CONNECTIONS)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.connections.locked():
            writer.close()
            return
        async with self.connections:
            try:
                data = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout=READ_TIMEOUT_SECONDS)
                request_line = data[:-2].decode("utf-8", errors="replace")
                method, path = "", ""
                parts = request_line.split(" ")
                if len(parts) >= 2:
                    method, path = parts[0], parts[1]
                if method == "GET" and path == HEALTH_PATH:
                    ready, payload = channel_readiness(self.channels)
                    payload["runtime"] = asdict(self.identity)
                    payload["maintenance"] = self.admission.paused
                    body = json.dumps(payload)
                    status = "200 OK" if ready else "503 Service Unavailable"
                    content_type = "application/json"
                else:
                    body, status, content_type = "Not Found", "404 Not Found", "text/plain"
                response = (
                    f"HTTP/1.0 {status}\r\nContent-Type: {content_type}\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"
                )
                writer.write(response.encode())
                await writer.drain()
            except (TimeoutError, ConnectionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                pass
            finally:
                writer.close()

    async def serve(self, host: str, port: int) -> None:
        server = await asyncio.start_server(self.handle, host, port, limit=4096)
        async with server:
            self.on_listening(host, server.sockets[0].getsockname()[1])
            await server.serve_forever()
