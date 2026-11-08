"""Parse message references, then revalidate and commit their ordered attachment batch."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.utils.text import safe_filename

from cirno_server.channels.websocket.attachment_policy import validate_attachment_batch
from cirno_server.channels.websocket.attachment_store import (
    AttachmentStore,
    AttachmentUploadError,
    StagedAttachment,
)
from cirno_server.webui.attachments import LocalAttachment, inspect_local_attachment


@dataclass(frozen=True)
class ParsedAttachments:
    references: list[str]
    local_paths: list[str]
    names: list[str | None]
    order: list[tuple[bool, int]]


@dataclass(frozen=True)
class CommittedAttachments:
    paths: list[str]
    local: list[LocalAttachment]
    uploaded: list[StagedAttachment]


def parse_message_attachments(raw_media: object, *, max_count: int) -> ParsedAttachments:
    if not isinstance(raw_media, list):
        raise AttachmentUploadError("malformed")
    attachments = cast(list[Any], raw_media)
    if len(attachments) > max_count + 1:
        raise AttachmentUploadError("Too many attachments")
    references: list[str] = []
    local_paths: list[str] = []
    names: list[str | None] = []
    order: list[tuple[bool, int]] = []
    for item in attachments:
        if not isinstance(item, dict):
            raise AttachmentUploadError("malformed")
        attachment = cast(dict[str, Any], item)
        reference = attachment.get("reference")
        path = attachment.get("path")
        if "data_url" in attachment or (reference is None) == (path is None):
            raise AttachmentUploadError("Expected an upload reference or local path")
        if path is not None:
            if not isinstance(path, str) or not path or len(path) > 4096:
                raise AttachmentUploadError("Invalid local attachment path")
            order.append((True, len(local_paths)))
            local_paths.append(path)
        else:
            if not isinstance(reference, str) or len(reference) > 64:
                raise AttachmentUploadError("Invalid upload reference")
            order.append((False, len(references)))
            references.append(reference)
        name = attachment.get("name")
        names.append((safe_filename(name) or None) if isinstance(name, str) else None)
    return ParsedAttachments(references, local_paths, names, order)


async def commit_message_attachments(
    attachments: ParsedAttachments,
    *,
    scope: WorkspaceScope,
    store: AttachmentStore,
    owner: str,
) -> CommittedAttachments:
    local = [
        await asyncio.to_thread(inspect_local_attachment, path, scope=scope, limits=store.limits)
        for path in attachments.local_paths
    ]
    uploaded = store.inspect(attachments.references, owner=owner) if attachments.references else []
    validate_attachment_batch(
        [item["mime"] for item in local] + [item.mime for item in uploaded], limits=store.limits
    )
    paths = [
        local[index]["path"] if is_local else str(uploaded[index].path)
        for is_local, index in attachments.order
    ]
    if len(set(paths)) != len(paths):
        raise AttachmentUploadError("Duplicate attachment reference")
    if attachments.references:
        store.commit(attachments.references, owner=owner)
    return CommittedAttachments(paths, local, uploaded)
