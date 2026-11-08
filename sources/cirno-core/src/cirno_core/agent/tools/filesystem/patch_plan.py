"""Validate a bounded edit batch before committing any of its files."""

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any

from cirno_core.agent.tools.filesystem.edit_io import (
    MAX_PATCH_BYTES,
    check_edit_size,
    read_edit_snapshot,
)
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.file_transactions import file_write_transaction


def _append(content: str, edit: dict[str, Any]) -> str:
    extra = edit["new_text"].replace("\r\n", "\n")
    if content and extra and not content.endswith("\n") and not extra.startswith("\n"):
        content += "\n"
    return content + extra


def _replace(content: str, edit: dict[str, Any]) -> str:
    old = edit.get("old_text")
    if not isinstance(old, str) or not old:
        raise ValueError("old_text required for replace")
    old = old.replace("\r\n", "\n")
    pos = content.find(old)
    if pos < 0:
        raise ValueError("old_text not found")
    if content.find(old, pos + 1) >= 0:
        raise ValueError("old_text appears multiple times")
    return content[:pos] + edit["new_text"].replace("\r\n", "\n") + content[pos + len(old) :]


_EDIT_ACTIONS = {"add": _append, "replace": _replace}


@dataclass
class PatchPlan:
    originals: dict[Path, str | None] = field(default_factory=dict)
    writes: dict[Path, str] = field(default_factory=dict)
    actions: dict[Path, str] = field(default_factory=dict)
    _original_bytes: int = 0
    _write_bytes: int = 0

    def add(self, source: Path, edit: dict[str, Any]) -> None:
        action = edit.get("action")
        if not isinstance(action, str) or action not in _EDIT_ACTIONS:
            raise ValueError(f"unknown action: {action}")
        if not isinstance(edit.get("new_text"), str):
            raise ValueError(f"new_text required for {action}: {source}")

        if source not in self.originals:
            original = read_edit_snapshot(source) if source.exists() else None
            if action == "replace" and original is None:
                raise ValueError(f"file to update does not exist: {source.name}")
            self.originals[source] = original
            self.actions[source] = "update" if original is not None else "add"
            self._original_bytes += len((original or "").encode("utf-8"))

        content = self.writes.get(source, self.originals[source] or "")
        try:
            updated = _EDIT_ACTIONS[action](content.replace("\r\n", "\n"), edit)
        except ValueError as exc:
            raise ValueError(f"{exc} in {source}") from exc
        if updated and not updated.endswith("\n"):
            updated += "\n"
        if "\r\n" in content:
            updated = updated.replace("\n", "\r\n")
        check_edit_size(updated, source)
        previous_size = len(self.writes.get(source, "").encode("utf-8"))
        self._write_bytes += len(updated.encode("utf-8")) - previous_size
        if self._original_bytes + self._write_bytes > MAX_PATCH_BYTES:
            raise ValueError("Patch exceeds the 8 MiB edit budget; split it into smaller batches.")
        self.writes[source] = updated

    def commit(self, cancelled: Event | None = None) -> None:
        with file_write_transaction(self.writes, cancelled=cancelled):
            self._commit()

    def _commit(self) -> None:
        for path, original in self.originals.items():
            current = read_edit_snapshot(path) if path.exists() else None
            if current != original:
                raise ValueError(
                    f"File changed while preparing the patch: {path}. Read it again before editing."
                )
        attempted: list[Path] = []
        try:
            for path, content in self.writes.items():
                # Include this file if directory fsync fails after its rename.
                attempted.append(path)
                atomic_write_text(path, content)
        except Exception as failure:
            rollback_errors: list[str] = []
            for path in reversed(attempted):
                try:
                    original = self.originals[path]
                    if original is None:
                        path.unlink(missing_ok=True)
                    elif read_edit_snapshot(path) != original:
                        atomic_write_text(path, original)
                except Exception as exc:
                    rollback_errors.append(f"{path}: {exc}")
            if rollback_errors:
                raise OSError(
                    f"{failure}; could not restore files: {'; '.join(rollback_errors)}"
                ) from failure
            raise
