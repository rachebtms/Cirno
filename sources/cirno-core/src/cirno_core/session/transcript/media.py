"""Media for durable conversation presentation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Mapping, cast
from urllib.parse import unquote, urlparse

from .contracts import (
    _INLINE_MARKDOWN_IMAGE_EXTS,
    _INLINE_MARKDOWN_MEDIA_EXTS,
    _INLINE_MARKDOWN_VIDEO_EXTS,
    _MARKDOWN_LOCAL_IMAGE_RE,
)


def rewrite_local_markdown_images(
    text: str,
    *,
    workspace_path: Path,
    sign_path: Callable[[Path], Mapping[str, Any] | None],
) -> str:
    """Rewrite markdown media paths inside the workspace to signed WebUI media URLs."""
    if "![" not in text:
        return text

    def resolve_url(raw_url: str) -> str | None:
        url = raw_url.strip()
        if url.startswith("<") and url.endswith(">"):
            url = url[1:-1].strip()
        if not url or url.startswith(("/v0/media/", "#")):
            return None
        parsed = urlparse(url)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            return None
        path_text = unquote(url)
        if Path(path_text).suffix.lower() not in _INLINE_MARKDOWN_MEDIA_EXTS:
            return None
        candidate = Path(path_text).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(workspace_path)
        except (OSError, ValueError):
            return None
        if not resolved.is_file():
            return None
        signed = sign_path(resolved)
        return str(signed.get("url")) if signed and signed.get("url") else None

    def replace(match: re.Match[str]) -> str:
        signed_url = resolve_url(match.group(2))
        if not signed_url:
            return match.group(0)
        title = match.group(3) or ""
        return f"![{match.group(1)}]({signed_url}{title})"

    return _MARKDOWN_LOCAL_IMAGE_RE.sub(replace, text)


def _media_kind_from_name(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in _INLINE_MARKDOWN_IMAGE_EXTS:
        return "image"
    if ext in _INLINE_MARKDOWN_VIDEO_EXTS:
        return "video"
    return "file"


def _media_from_signed_urls(value: Any) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    urls = cast(list[Any], value) if isinstance(value, list) else []
    for m in urls:
        if isinstance(m, dict):
            media_item = cast(dict[str, Any], m)
            if not media_item.get("url"):
                continue
            name = str(media_item.get("name") or "")
            media.append(
                {
                    "kind": _media_kind_from_name(name),
                    "url": str(media_item["url"]),
                    "name": name,
                },
            )
    return media
