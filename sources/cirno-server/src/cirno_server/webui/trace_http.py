"""Authenticated ZIP transfer of the current tab's complete recording."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
from uuid import UUID

from aiohttp import web
from cirno_core.observability.recordings import current_recordings
from cirno_core.utils.cancellation import shield_and_drain


class TraceHTTP:
    def __init__(self, uploads):
        self.uploads = uploads

    async def handle(self, request: web.BaseRequest) -> web.StreamResponse:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer ") or not self.uploads.authorized(authorization[7:]):
            return web.json_response({"error": "Unauthorized"}, status=401, headers={"Cache-Control": "no-store"})
        if request.method != "POST" or request.path != "/v0/traces/export":
            return web.json_response({"error": "Not found"}, status=404)
        with tempfile.TemporaryDirectory(prefix="cirno-trace-download-") as folder:
            path = Path(folder) / "recording.zip"
            try:
                data = bytearray()
                async for chunk in request.content.iter_chunked(1024):
                    data.extend(chunk)
                    if len(data) > 4096:
                        raise ValueError("Trace export options are too large")
                values = json.loads(data)
                identifier, epoch = str(UUID(values["recording_id"])), values["epoch"]
                await shield_and_drain(asyncio.to_thread(current_recordings().export, identifier, epoch, path))
            except KeyError:
                return web.json_response({"error": "Recording is no longer available"}, status=404)
            except (ValueError, TypeError, OSError, sqlite3.Error) as error:
                return web.json_response({"error": str(error)}, status=400)
            response = web.StreamResponse(headers={
                "Content-Type": "application/zip", "Cache-Control": "no-store",
                "Content-Length": str(path.stat().st_size),
                "Content-Disposition": f'attachment; filename="cirno-trace-{identifier}.zip"',
            })
            await response.prepare(request)
            with path.open("rb") as stream:
                while chunk := await shield_and_drain(asyncio.to_thread(stream.read, 65536)):
                    await response.write(chunk)
            await response.write_eof()
            return response
