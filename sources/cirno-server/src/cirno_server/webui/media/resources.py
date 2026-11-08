"""Authorize one exact media resource without loading its contents."""

from __future__ import annotations

import binascii
import hashlib
import hmac
import json
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cirno_core.security.workspace_access import WorkspaceScope, build_workspace_scope
from cirno_server.webui.file_preview import WebUIFilePreviewError, resolve_file_path
from .signing import MediaDirProvider, b64url_decode

_ALLOWED_MIMES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/svg+xml",
        "video/mp4",
        "video/webm",
        "video/quicktime",
    }
)


class MediaAccessError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class MediaResource:
    path: Path
    borrowed: bool

    @property
    def headers(self) -> dict[str, str]:
        mime = mimetypes.guess_type(self.path.name)[0] or "application/octet-stream"
        headers = {
            "Content-Type": mime if mime in _ALLOWED_MIMES else "application/octet-stream",
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-store"
            if self.borrowed
            else "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        }
        if mime == "image/svg+xml":
            headers["Content-Security-Policy"] = (
                "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
            )
        return headers


def authorize_media_reference(
    sig: str,
    payload: str,
    *,
    secret: bytes,
    media_dir: MediaDirProvider,
    scope_for_session: Callable[[str], WorkspaceScope | None] | None = None,
) -> MediaReference:
    try:
        provided_mac = b64url_decode(sig)
        expected_mac = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()[:16]
    except (ValueError, binascii.Error, UnicodeEncodeError) as exc:
        raise MediaAccessError(401, "invalid signature") from exc
    if not hmac.compare_digest(expected_mac, provided_mac):
        raise MediaAccessError(401, "invalid signature")
    try:
        reference = b64url_decode(payload).decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise MediaAccessError(400, "invalid payload") from exc
    borrowed = reference.startswith(("\0", "\1"))
    if borrowed:
        try:
            raw: object = json.loads(reference[1:])
            if not isinstance(raw, list):
                raise ValueError("invalid attachment reference")
            items = cast(list[object], raw)
            if not all(isinstance(value, str) for value in items):
                raise ValueError("invalid attachment reference")
            values = cast(list[str], items)
            if reference.startswith("\1"):
                if len(values) != 3:
                    raise ValueError("invalid workspace attachment")
                root, access_mode, path = values
                scope = build_workspace_scope(root, access_mode)
            else:
                if len(values) != 2 or scope_for_session is None:
                    raise ValueError("invalid local attachment")
                session_key, path = values
                scope = scope_for_session(session_key)
            if scope is None:
                raise MediaAccessError(404, "attachment unavailable")
            return MediaReference(path, scope, media_dir)
        except MediaAccessError:
            raise
        except ValueError as exc:
            raise MediaAccessError(400, "invalid attachment reference") from exc
    return MediaReference(reference, None, media_dir)


@dataclass(frozen=True)
class MediaReference:
    value: str
    scope: WorkspaceScope | None
    media_dir: MediaDirProvider

    def resolve(self) -> MediaResource:
        if self.scope is not None:
            try:
                path = resolve_file_path(self.value, scope=self.scope, literal=True)
            except WebUIFilePreviewError as exc:
                raise MediaAccessError(exc.status, "attachment unavailable") from exc
            return MediaResource(path, True)
        try:
            root = self.media_dir(None).resolve()
            path = (root / self.value).resolve()
            path.relative_to(root)
        except (OSError, ValueError) as exc:
            raise MediaAccessError(404, "not found") from exc
        if not path.is_file():
            raise MediaAccessError(404, "not found")
        return MediaResource(path, False)
