"""Readiness is independent of TCP packet boundaries and reflects live state."""

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from types import SimpleNamespace

from cirno_core.runtime.admission import RuntimeAdmission
from cirno_server.lifecycle.contracts import ServerHealthIdentity
from cirno_server.lifecycle.health_server import HealthListener


@asynccontextmanager
async def listener():
    bound = asyncio.get_running_loop().create_future()
    channels = SimpleNamespace(
        enabled_channels=["websocket"],
        get_status=lambda: {"websocket": {"running": True, "state": "running"}},
    )
    owner = HealthListener(channels, RuntimeAdmission(), ServerHealthIdentity("instance", "run", "0.2.0"),
                           on_listening=lambda _host, port: bound.set_result(port))
    task = asyncio.create_task(owner.serve("127.0.0.1", 0))
    try:
        yield owner, channels, await asyncio.wait_for(bound, 3)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def test_health_waits_for_the_complete_request_line():
    async with listener() as (owner, _, port):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(b"GET /v0/hea")
            await writer.drain()
            # Let the server consume the first fragment before the rest arrives.
            await asyncio.sleep(.02)
            writer.write(b"lth HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(), 3)
            status, body = data.split(b"\r\n\r\n", 1)
            assert status.startswith(b"HTTP/1.0 200 OK"), data
            payload = json.loads(body)
            assert payload["runtime"] == {"instance_id": "instance", "run_id": "run", "version": "0.2.0"}
            assert payload["ready"] and payload["maintenance"] is False
        finally:
            writer.close()
            await writer.wait_closed()


async def test_health_reports_current_readiness_after_binding():
    async with listener() as (_, channels, port):
        channels.get_status = lambda: {"websocket": {"running": False, "state": "failed"}}
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            writer.write(b"GET /v0/health HTTP/1.1\r\n\r\n")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(), 3)
            assert data.startswith(b"HTTP/1.0 503 Service Unavailable")
            assert json.loads(data.split(b"\r\n\r\n", 1)[1])["websocket"] == "failed"
        finally:
            writer.close()
            await writer.wait_closed()
