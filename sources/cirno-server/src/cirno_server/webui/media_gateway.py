"""Media gateway services shared by WebUI HTTP routes and WebSocket frames."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cirno_core.config.paths import get_media_dir
from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.session.transcript import rewrite_local_markdown_images
from cirno_server.webui.media.signing import (
    media_attachment_kind,
    sign_local_attachment,
    sign_workspace_attachment,
    sign_media_path,
    sign_or_stage_media_path,
    signed_media_attachments,
)
from cirno_server.webui.media.resources import (
    MediaReference,
    MediaResource,
    authorize_media_reference,
)


def _default_media_dir(channel: str | None) -> Path:
    return get_media_dir(channel)


class WebUIMediaServer:
    """Own media URL signing and WebUI markdown/media augmentation."""

    def __init__(
        self,
        *,
        workspace_path: Path,
        logger: Any,
        media_dir: Callable[[str | None], Path] | None = None,
        secret: bytes | None = None,
    ) -> None:
        self.workspace_path = workspace_path
        self.logger = logger
        self._media_dir: Callable[[str | None], Path] = media_dir or _default_media_dir
        self.secret = secret or secrets.token_bytes(32)

    def resolve_signed_media(
        self,
        sig: str,
        payload: str,
        *,
        scope_for_session: Callable[[str], WorkspaceScope | None] | None = None,
    ) -> MediaResource:
        return self.authorize_media_reference(
            sig, payload, scope_for_session=scope_for_session
        ).resolve()

    def authorize_media_reference(
        self,
        sig: str,
        payload: str,
        *,
        scope_for_session: Callable[[str], WorkspaceScope | None] | None = None,
    ) -> MediaReference:
        return authorize_media_reference(
            sig,
            payload,
            secret=self.secret,
            media_dir=self._media_dir,
            scope_for_session=scope_for_session,
        )

    def sign_or_stage_media_path(self, path: Path) -> dict[str, str] | None:
        return sign_or_stage_media_path(
            path,
            secret=self.secret,
            media_dir=self._media_dir,
            logger=self.logger,
        )

    def rewrite_local_markdown_images(
        self,
        text: str,
        *,
        workspace_path: Path | None = None,
    ) -> str:
        return rewrite_local_markdown_images(
            text,
            workspace_path=workspace_path or self.workspace_path,
            sign_path=self.sign_or_stage_media_path,
        )

    def augment_transcript_media(self, paths: list[str]) -> list[dict[str, Any]]:
        return signed_media_attachments(
            paths,
            sign_path=self.sign_or_stage_media_path,
        )

    def local_attachment_url(self, path: str, *, session_key: str) -> str:
        return sign_local_attachment(path, session_key=session_key, secret=self.secret)

    def workspace_media_url(
        self, path: str, *, scope: WorkspaceScope, session_key: str | None
    ) -> str:
        if session_key is not None:
            return self.local_attachment_url(path, session_key=session_key)
        return sign_workspace_attachment(path, scope=scope, secret=self.secret)

    def augment_transcript_user_media(
        self,
        paths: list[str],
        local_paths: list[str],
        *,
        session_key: str,
    ) -> list[dict[str, Any]]:
        local = set(local_paths)
        media: list[dict[str, Any]] = []
        for raw in paths:
            path = Path(raw)
            try:
                if not path.is_file():
                    url = ""
                elif raw in local:
                    url = self.local_attachment_url(raw, session_key=session_key)
                else:
                    url = sign_media_path(path, secret=self.secret, media_dir=self._media_dir) or ""
            except OSError:
                url = ""
            media.append({"kind": media_attachment_kind(path.name), "name": path.name, "url": url})
        return media
