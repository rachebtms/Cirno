"""Small HTTP-only entry surface available before a WebUI socket can be issued."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections import deque
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web
from cirno.webui.auth.store import SESSION_SECONDS, AccountError, AccountStore

COOKIE_NAME = "cirno_session"


class BrowserAuth:
    def __init__(self, store: AccountStore, *, enabled: bool) -> None:
        self.store = store
        self.enabled = enabled or store.path.exists()
        self._failures: deque[float] = deque(maxlen=10)
        self._lock = asyncio.Lock()

    @staticmethod
    def cookie(headers: Any) -> str:
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get("Cookie", ""))
        except CookieError:
            return ""
        value = cookies.get(COOKIE_NAME)
        return value.value if value else ""

    def authenticated(self, headers: Any) -> bool:
        return self.enabled and self.store.authenticated(self.cookie(headers))

    def status(self, headers: Any) -> dict[str, Any]:
        owner = self.store.owner() if self.enabled else None
        return {
            "enabled": self.enabled,
            "registration_required": self.enabled and owner is None,
            "authenticated": self.authenticated(headers),
        }

    async def handle(self, request: web.BaseRequest) -> web.StreamResponse:
        try:
            response = await self._handle(request)
        except AccountError as exc:
            response = web.json_response({"error": exc.code}, status=exc.status)
        except (OSError, sqlite3.Error) as exc:
            # Persistence failures must be visible and diagnosed, never treated as a new instance.
            from loguru import logger
            logger.exception("Browser account operation failed: {}", type(exc).__name__)
            response = web.json_response({"error": "storage_failed"}, status=500)
        response.headers["Cache-Control"] = "no-store"
        response.force_close()
        return response

    async def _handle(self, request: web.BaseRequest) -> web.Response:
        if request.method != "POST":
            raise AccountError("method_not_allowed", 405)
        if not self.enabled:
            raise AccountError("registration_disabled", 403)
        origin = request.headers.get("Origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
            origin and urlsplit(origin).netloc.lower() != request.host.lower()
        ):
            raise AccountError("invalid_origin", 403)
        if request.content_type != "application/json":
            raise AccountError("invalid_request", 415)
        if (request.content_length is not None and request.content_length > 8192) or request.headers.get("Content-Encoding"):
            raise AccountError("invalid_request", 413)
        try:
            async with asyncio.timeout(10):
                data = bytearray()
                async for chunk in request.content.iter_chunked(8192):
                    if len(data) + len(chunk) > 8192:
                        raise AccountError("invalid_request", 413)
                    data.extend(chunk)
                body = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError, TimeoutError) as exc:
            raise AccountError("invalid_request") from exc
        if not isinstance(body, dict):
            raise AccountError("invalid_request")

        action = request.path.removeprefix("/api/auth/")
        if action in {"logout", "complete"}:
            if action == "complete" and not await asyncio.to_thread(self.authenticated, request.headers):
                raise AccountError("unauthorized", 401)
            if action == "complete":
                await asyncio.to_thread(self.store.complete_onboarding)
            else:
                await asyncio.to_thread(self.store.logout, self.cookie(request.headers))
            response = web.json_response({"ok": True})
            if action == "logout":
                response.del_cookie(COOKIE_NAME, path="/", samesite="Strict", httponly=True)
            return response
        if action not in {"register", "login"}:
            raise AccountError("not_found", 404)
        async with self._lock:
            now = time.monotonic()
            while self._failures and now - self._failures[0] > 60:
                self._failures.popleft()
            if len(self._failures) == self._failures.maxlen:
                raise AccountError("too_many_attempts", 429)
            try:
                token = await asyncio.to_thread(
                    self.store.register if action == "register" else self.store.login,
                    body.get("username"), body.get("password"),
                )
            except AccountError:
                self._failures.append(time.monotonic())
                raise
        response = web.json_response({"ok": True}, status=201 if action == "register" else 200)
        response.set_cookie(
            COOKIE_NAME, token, max_age=SESSION_SECONDS, path="/", httponly=True,
            samesite="Strict", secure=request.secure or request.headers.get("X-Forwarded-Proto") == "https",
        )
        return response
