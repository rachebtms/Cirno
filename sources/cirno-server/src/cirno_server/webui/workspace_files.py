"""Browse and edit files under a conversation's existing workspace policy."""

from __future__ import annotations

import heapq
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cirno_core.security.workspace_access import WorkspaceScope
from cirno_core.security.workspace_policy import WorkspaceBoundaryError, resolve_allowed_path
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.file_transactions import file_write_transaction
from cirno_server.webui.file_preview import (
    MAX_FILE_PREVIEW_BYTES,
    WebUIFilePreviewError,
    file_preview_payload,
)

MAX_DIRECTORY_ENTRIES = 500


def _resolve(path: str, scope: WorkspaceScope, *, strict: bool = True) -> Path:
    try:
        return resolve_allowed_path(
            path or str(scope.project_path), workspace=scope.project_path,
            allowed_root=scope.project_path if scope.restrict_to_workspace else None, strict=strict,
        )
    except WorkspaceBoundaryError as exc:
        raise WebUIFilePreviewError(403, "Path is outside the current workspace") from exc
    except FileNotFoundError as exc:
        raise WebUIFilePreviewError(404, "Path does not exist") from exc


def list_workspace_files(path: str, *, scope: WorkspaceScope, query: str = "", show_hidden: bool = False) -> dict[str, Any]:
    directory = _resolve(path, scope)
    if not directory.is_dir():
        raise WebUIFilePreviewError(400, "Choose a directory")
    with os.scandir(directory) as entries:
        selected = heapq.nsmallest(MAX_DIRECTORY_ENTRIES + 1, (
            {"name": entry.name, "path": str(directory / entry.name),
             "kind": "directory" if entry.is_dir() else "file"}
            for entry in entries
            if (show_hidden or not entry.name.startswith(".")) and query.casefold() in entry.name.casefold()
        ), key=lambda entry: (entry["kind"] != "directory", entry["name"].casefold()))
    at_root = directory == scope.project_path and scope.restrict_to_workspace
    return {"path": str(directory), "project_path": str(scope.project_path),
            "parent": None if at_root or directory.parent == directory else str(directory.parent),
            "entries": selected[:MAX_DIRECTORY_ENTRIES], "truncated": len(selected) > MAX_DIRECTORY_ENTRIES}


def read_workspace_file(path: str, *, scope: WorkspaceScope, media_url: Callable[[Path], str] | None = None) -> dict[str, Any]:
    resolved = _resolve(path, scope)
    return file_preview_payload(str(resolved), scope=scope, literal=True, editing=True, media_url=media_url)


def save_workspace_file(path: str, content: str, revision: str, *, scope: WorkspaceScope) -> dict[str, Any]:
    if len(content.encode("utf-8")) > MAX_FILE_PREVIEW_BYTES:
        raise WebUIFilePreviewError(413, "Text files larger than 384 KiB cannot be edited")
    with file_write_transaction([_resolve(path, scope)]):
        current = read_workspace_file(path, scope=scope)
        if not current["editable"]:
            raise WebUIFilePreviewError(415, "This file is available for preview only")
        if current["revision"] != revision:
            raise WebUIFilePreviewError(409, "The file changed. Reload it before saving your edits.")
        resolved = _resolve(path, scope)
        atomic_write_text(resolved, content)
        return read_workspace_file(str(resolved), scope=scope)


def create_workspace_entry(path: str, kind: str, *, scope: WorkspaceScope) -> dict[str, str]:
    resolved = _resolve(path, scope, strict=False)
    if kind == "directory":
        resolved.mkdir()
    elif kind == "file":
        with file_write_transaction([resolved]):
            with resolved.open("x", encoding="utf-8"):
                pass
    else:
        raise WebUIFilePreviewError(400, "Choose a file or directory")
    return {"path": str(resolved), "kind": kind}
