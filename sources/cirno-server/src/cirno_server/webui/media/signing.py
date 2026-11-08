"""Signed references and attachment projection; no file-body reads."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cirno_core.config.paths import get_media_dir
from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.utils.text import safe_filename

MediaDirProvider = Callable[[str | None], Path]
SignedMediaPath = Callable[[Path], dict[str, str] | None]


def b64url_encode(data: bytes) -> str:
    """URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    """Reverse of :func:`b64url_encode`; caller handles decode errors."""
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _default_media_dir(channel: str | None = None) -> Path:
    return get_media_dir(channel)


def sign_media_path(
    abs_path: Path,
    *,
    secret: bytes,
    media_dir: MediaDirProvider = _default_media_dir,
) -> str | None:
    """Return a signed ``/v0/media/<sig>/<payload>`` URL for a media-root path."""
    try:
        media_root = media_dir(None).resolve()
        rel = abs_path.resolve().relative_to(media_root)
    except (OSError, ValueError):
        return None
    payload = b64url_encode(rel.as_posix().encode("utf-8"))
    mac = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()[:16]
    return f"/v0/media/{b64url_encode(mac)}/{payload}"


def sign_local_attachment(path: str, *, session_key: str, secret: bytes) -> str:
    """Bind a borrowed path to its session; serving rechecks the current scope."""
    payload = b64url_encode(
        b"\0" + json.dumps([session_key, path], ensure_ascii=False).encode("utf-8")
    )
    mac = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()[:16]
    return f"/v0/media/{b64url_encode(mac)}/{payload}"


def sign_workspace_attachment(path: str, *, scope: WorkspaceScope, secret: bytes) -> str:
    """Grant a draft tab access to one exact file within its selected scope."""
    reference = [str(scope.project_path), scope.access_mode, path]
    payload = b64url_encode(b"\1" + json.dumps(reference, ensure_ascii=False).encode("utf-8"))
    mac = hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest()[:16]
    return f"/v0/media/{b64url_encode(mac)}/{payload}"


def sign_or_stage_media_path(
    path: Path,
    *,
    secret: bytes,
    media_dir: MediaDirProvider = _default_media_dir,
    logger: Any | None = None,
) -> dict[str, str] | None:
    """Sign an existing media-root path, or stage an arbitrary file before signing."""
    signed = sign_media_path(path, secret=secret, media_dir=media_dir)
    if signed is not None:
        return {"url": signed, "name": path.name}
    staged_tmp: Path | None = None
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            return None
        source_stat = resolved.stat()
        target_dir = media_dir("websocket")
        safe_name = safe_filename(path.name) or "attachment"
        source_version = "\0".join(
            (
                os.path.normcase(str(resolved)),
                str(source_stat.st_size),
                str(source_stat.st_mtime_ns),
                str(source_stat.st_ctime_ns),
            )
        )
        source_digest = hashlib.sha256(source_version.encode("utf-8")).hexdigest()[:20]
        staged = target_dir / f"{source_digest}-{safe_name}"
        if not staged.is_file() or staged.stat().st_size != source_stat.st_size:
            staged_tmp = target_dir / f".{source_digest}-{uuid.uuid4().hex}.tmp"
            shutil.copyfile(resolved, staged_tmp)
            staged_tmp.replace(staged)
    except OSError as exc:
        if logger is not None:
            logger.warning("failed to stage outbound media {}: {}", path, exc)
        return None
    finally:
        if staged_tmp is not None:
            staged_tmp.unlink(missing_ok=True)
    signed = sign_media_path(staged, secret=secret, media_dir=media_dir)
    if signed is None:
        return None
    return {"url": signed, "name": path.name}


def media_attachment_kind(name: str) -> str:
    """Infer the WebUI media attachment kind from a filename."""
    mime, _ = mimetypes.guess_type(name)
    if mime and mime.startswith("video/"):
        return "video"
    if mime and mime.startswith("image/"):
        return "image"
    return "file"


def signed_media_attachments(
    paths: list[str],
    *,
    sign_path: SignedMediaPath,
) -> list[dict[str, Any]]:
    """Keep every attachment in order, signing only files available at projection time."""
    out: list[dict[str, Any]] = []
    for pstr in paths:
        path = Path(pstr)
        try:
            att = sign_path(path) if path.is_file() else None
        except OSError:
            att = None
        name = (att.get("name") if att else None) or path.name
        url = (att.get("url") if att else None) or ""
        out.append({"kind": media_attachment_kind(name), "url": url, "name": name})
    return out
