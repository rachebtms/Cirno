"""Edit the assistant's Home files through authenticated settings requests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cirno.config.home import get_home_path
from cirno.webui.settings.contracts import WebUISettingsError

PROFILE_FILES = {
    "soul": "SOUL.md",
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
    """Preserve edits made by Dream or another browser since this file was read."""
    if profile_payload(name)["revision"] != revision:
        raise WebUISettingsError("This Home file changed. Reload it before saving.", status=409)
    path = _profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    from cirno.utils.atomic_file import atomic_write_text

    atomic_write_text(path, content)
    return profile_payload(name)
