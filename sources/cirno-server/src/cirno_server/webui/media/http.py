"""Backpressured attachment transfer on the existing body-capable HTTP listener."""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import ExitStack
from typing import TYPE_CHECKING

from aiohttp import web
from cirno_core.utils.atomic_file import open_atomic_snapshot
from cirno_core.utils.cancellation import shield_and_drain
from .ranges import parse_byte_range
from .resources import MediaAccessError

if TYPE_CHECKING:
    from cirno_core.security.workspace_access import WorkspaceScope
    from collections.abc import Callable
    from cirno_server.webui.media_gateway import WebUIMediaServer

MEDIA_CHUNK_BYTES = 64 * 1024
_MEDIA_ROUTE = re.compile(r"^/v0/media/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)$")


class MediaHTTP:
    def __init__(
        self, media: WebUIMediaServer, scope_for_session: Callable[[str], WorkspaceScope | None]
    ) -> None:
        self.media = media
        self.scope_for_session = scope_for_session

    async def handle(self, request: web.BaseRequest) -> web.StreamResponse:
        if request.method not in {"GET", "HEAD"}:
            response = web.Response(
                status=405, text="Use GET or HEAD", headers={"Allow": "GET, HEAD"}
            )
        else:
            match = _MEDIA_ROUTE.fullmatch(request.path)
            if match is None:
                response = web.Response(status=404, text="Not found")
            else:
                try:
                    return await self._stream(request, *match.groups())
                except MediaAccessError as exc:
                    response = web.Response(status=exc.status, text=str(exc))
        response.headers["Cache-Control"] = "no-store"
        response.force_close()
        return response

    async def _stream(self, request: web.BaseRequest, sig: str, payload: str) -> web.StreamResponse:
        # Session scope belongs to its event-loop owner; only immutable path
        # authorization crosses into the filesystem worker.
        reference = self.media.authorize_media_reference(
            sig, payload, scope_for_session=self.scope_for_session
        )
        resource = await asyncio.to_thread(reference.resolve)
        # ExitStack retains an opened snapshot even if Stop arrives during open.
        # Each disk operation settles before that snapshot can be closed.
        with ExitStack() as files:
            try:
                stream = await shield_and_drain(
                    asyncio.to_thread(
                        lambda: files.enter_context(open_atomic_snapshot(resource.path)),
                    )
                )
            except FileNotFoundError as exc:
                raise MediaAccessError(404, "attachment unavailable") from exc
            except PermissionError as exc:
                raise MediaAccessError(403, str(exc)) from exc
            size = os.fstat(stream.fileno()).st_size
            headers = resource.headers
            start, end = 0, size - 1
            range_value = request.headers.get("Range", "")
            if range_value:
                try:
                    start, end = parse_byte_range(range_value, size)
                except ValueError:
                    response = web.Response(
                        status=416,
                        text="range not satisfiable",
                        headers={
                            **headers,
                            "Content-Range": f"bytes */{size}",
                        },
                    )
                    response.force_close()
                    return response
                headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            remaining = end - start + 1
            headers["Content-Length"] = str(remaining)
            response = web.StreamResponse(status=206 if range_value else 200, headers=headers)
            response.force_close()
            await response.prepare(request)
            if request.method != "HEAD":
                await shield_and_drain(asyncio.to_thread(stream.seek, start))
                while remaining:
                    chunk = await shield_and_drain(
                        asyncio.to_thread(stream.read, min(remaining, MEDIA_CHUNK_BYTES))
                    )
                    if not chunk:
                        raise OSError("Media changed while streaming; reload the attachment")
                    await response.write(chunk)
                    remaining -= len(chunk)
            await response.write_eof()
            return response
