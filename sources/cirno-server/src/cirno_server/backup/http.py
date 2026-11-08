"""Authenticated, streaming backup transfer on the existing Web UI listener."""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
import sqlite3
import tarfile
import time

from aiohttp import web
from cirno_core.runtime.admission import RuntimeBusyError, RuntimeMaintenanceError
from cirno_core.utils.cancellation import shield_and_drain
from cirno_server.backup.archive import Backups


class BackupHTTP:
    def __init__(self, config_path, uploads, bus, sessions, *, maintenance=None):
        self.archive = Backups(config_path)
        self.uploads, self.bus, self.sessions = uploads, bus, sessions
        self.maintenance = maintenance or (
            lambda: self.bus.admission.pause_if_idle(
                lambda: bool(self.bus.inbound_size or self.bus.has_pending_events)
            )
        )
        self.lock = asyncio.Lock()
        self.downloads = {}

    def prune(self):
        now = time.monotonic()
        for ticket, (path, expires, owner) in list(self.downloads.items()):
            if expires < now:
                path.unlink(missing_ok=True)
                del self.downloads[ticket]
        # Staged imports remain until explicitly restored/cancelled.
        for path in (self.archive.store / "exports").glob("*.tar.gz"):
            if time.time() - path.stat().st_mtime > 3600:
                path.unlink(missing_ok=True)

    async def handle(self, request: web.BaseRequest) -> web.StreamResponse:
        try:
            response = await self._handle(request)
        except (ValueError, KeyError, OSError, tarfile.TarError, sqlite3.Error) as error:
            response = web.json_response({"error": str(error)}, status=400)
        except web.HTTPException as error:
            response = web.json_response({"error": error.text}, status=error.status)
        except (RuntimeBusyError, RuntimeMaintenanceError):
            response = web.json_response(
                {"error": "Finish or stop active work before exporting or restoring a backup."},
                status=409,
            )
        response.headers["Cache-Control"] = "no-store"
        response.force_close()
        return response

    async def _handle(self, request: web.BaseRequest) -> web.StreamResponse:
        if request.method == "GET" and request.path == "/v0/backups/download":
            token = request.query.get("ticket", "")
            path, expires, owner = self.downloads.get(token, (None, 0, ""))
            if path is None or expires < time.monotonic() or not self.uploads.authorized(owner):
                raise web.HTTPUnauthorized(text="Backup download expired. Export again.")
            # FileResponse streams through sendfile and supports browser range/resume.
            return web.FileResponse(
                path,
                headers={
                    "Content-Disposition": f'attachment; filename="{path.name}"',
                    "Cache-Control": "no-store",
                    "Content-Type": "application/gzip",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        owner = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if not self.uploads.authorized(owner):
            raise web.HTTPUnauthorized(text="Reconnect to Cirno before transferring backups.")
        if request.method != "POST":
            raise web.HTTPMethodNotAllowed(request.method, ["POST"])
        action = request.path.removeprefix("/v0/backups/")
        if action == "upload":
            if self.lock.locked():
                raise ValueError("Another backup operation is running.")
            async with self.lock:
                directory = self.archive.store / "uploads"
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                from uuid import uuid4

                path = directory / (uuid4().hex + ".tar.gz")
                try:
                    with path.open("xb") as output:
                        async for chunk in request.content.iter_chunked(1024 * 1024):
                            await shield_and_drain(asyncio.to_thread(output.write, chunk))
                    if not self.uploads.authorized(owner):
                        raise ValueError(
                            "Connection closed during upload. Reconnect and try again."
                        )
                    result = await shield_and_drain(asyncio.to_thread(self.archive.inspect, path))
                finally:
                    path.unlink(missing_ok=True)
                return web.json_response(result)
        data = bytearray()
        async for chunk in request.content.iter_chunked(65536):
            if len(data) + len(chunk) > 65536:
                raise ValueError("Backup options are too large.")
            data.extend(chunk)
        values = json.loads(data or b"{}")
        if not isinstance(values, dict):
            raise ValueError("Backup options must be an object.")
        if action == "catalog":
            return web.json_response(
                await asyncio.to_thread(self.archive.recommendations, self.sessions)
            )
        if self.lock.locked():
            raise ValueError("Another backup operation is running.")
        async with self.lock:
            if action == "export":
                # No cancellation or torn cross-database snapshot: ask the owner to finish tasks first.
                with self.maintenance():
                    path, manifest = await shield_and_drain(
                        asyncio.to_thread(self.archive.create, values.get("paths", []))
                    )
                self.prune()
                ticket = secrets.token_urlsafe(32)
                self.downloads[ticket] = (path, time.monotonic() + 3600, owner)
                return web.json_response(
                    {
                        "url": "/v0/backups/download?ticket=" + ticket,
                        "filename": path.name,
                        "manifest": manifest,
                    }
                )
            if action == "restore":
                with self.maintenance():
                    result = await shield_and_drain(
                        asyncio.to_thread(
                            self.archive.prepare_restore, values.get("id"), values.get("extras", {})
                        )
                    )
                return web.json_response(result)
            if action == "cancel":
                identifier = values.get("id")
                plan_path = self.archive.store / "restore-plan.json"
                plan = json.loads(plan_path.read_text()) if plan_path.exists() else None
                if identifier:
                    stage = self.archive._stage(identifier)
                    if plan and plan["id"] == identifier:
                        plan_path.unlink()
                    await asyncio.to_thread(shutil.rmtree, stage)
                else:
                    plan_path.unlink(missing_ok=True)
                return web.json_response({"ok": True})
        raise web.HTTPNotFound()
