"""Edit the assistant's Home files through authenticated settings requests."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Any

from cirno_core.config.home import get_home_path
from cirno_core.utils.atomic_file import read_atomic_bytes

from cirno_server.webui.settings.contracts import WebUISettingsError

PROFILE_FILES = {
    "soul": "SOUL.md",
    "worker": "WORKER.md",
    "user": "USER.md",
    "instructions": "AGENTS.md",
    "memory": "memory/MEMORY.md",
    "heartbeat": "HEARTBEAT.md",
}


def _profile_path(name: str, home_path: Path | None = None) -> Path:
    if name not in PROFILE_FILES:
        raise WebUISettingsError("Unknown Home file")
    return (home_path if home_path is not None else get_home_path()) / PROFILE_FILES[name]


def profile_payload(name: str, *, home_path: Path | None = None) -> dict[str, Any]:
    path = _profile_path(name, home_path)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise WebUISettingsError("Home path must be a regular file")
        content = read_atomic_bytes(path).decode("utf-8")
    except FileNotFoundError:
        content = ""
    # Preserve the universal-newline content and revisions used by the editor.
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    return {"name": name, "file": PROFILE_FILES[name], "content": content,
            "revision": hashlib.sha256(content.encode()).hexdigest()}


def update_profile(name: str, content: str, revision: str, *, home_path: Path | None = None) -> dict[str, Any]:
    """Compare and save under the same ownership used by consolidation edits."""
    from cirno_core.utils.atomic_file import atomic_write_text
    from cirno_core.utils.file_transactions import file_write_transaction

    home = (home_path if home_path is not None else get_home_path()).expanduser().resolve(strict=False)
    path = _profile_path(name, home)
    with file_write_transaction([path]):
        if profile_payload(name, home_path=home)["revision"] != revision:
            raise WebUISettingsError("This Home file changed. Reload it before saving.", status=409)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content)
        return profile_payload(name, home_path=home)
