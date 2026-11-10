"""Edit the assistant's Home files through authenticated settings requests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cirno_core.config.home import get_home_path
from cirno_server.webui.settings.contracts import WebUISettingsError

PROFILE_FILES = {
    "soul": "SOUL.md",
    "worker": "WORKER.md",
    "user": "USER.md",
    "instructions": "AGENTS.md",
    "memory": "memory/MEMORY.md",
    "heartbeat": "HEARTBEAT.md",
}


def _profile_path(name: str) -> Path:
    if name not in PROFILE_FILES:
        raise WebUISettingsError("Unknown Home file")
    return get_home_path() / PROFILE_FILES[name]


def profile_payload(name: str) -> dict[str, Any]:
    path = _profile_path(name)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"name": name, "file": PROFILE_FILES[name], "content": content,
            "revision": hashlib.sha256(content.encode()).hexdigest()}


def update_profile(name: str, content: str, revision: str) -> dict[str, Any]:
    """Compare and save under the same ownership used by consolidation edits."""
    from cirno_core.utils.atomic_file import atomic_write_text
    from cirno_core.utils.file_transactions import file_write_transaction

    path = _profile_path(name)
    with file_write_transaction([path]):
        if profile_payload(name)["revision"] != revision:
            raise WebUISettingsError("This Home file changed. Reload it before saving.", status=409)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content)
        return profile_payload(name)
