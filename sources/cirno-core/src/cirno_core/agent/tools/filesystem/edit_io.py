"""Shared bounded snapshots for edits that retain originals and calculate diffs."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event

from cirno_core.utils.atomic_file import atomic_write_text, read_atomic_bytes
from cirno_core.utils.file_edit_events import FileEditResult
from cirno_core.utils.file_transactions import file_write_transaction

MAX_EDIT_BYTES = 2 * 1024 * 1024
MAX_PATCH_BYTES = 8 * 1024 * 1024


def check_edit_size(content: str, path: Path) -> None:
    if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
        raise ValueError(
            f"File too large to edit: {path}. Maximum is 2 MiB; use a targeted shell command for larger files."
        )


def read_edit_snapshot(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"Not a regular file: {path}")
    raw = read_atomic_bytes(path, max_bytes=MAX_EDIT_BYTES + 1)
    if len(raw) > MAX_EDIT_BYTES:
        raise ValueError(
            f"File too large to edit: {path}. Maximum is 2 MiB; use a targeted shell command for larger files."
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"File is not UTF-8 text: {path}") from exc


@dataclass(frozen=True)
class PreparedEdit:
    path: Path
    before: str | None
    after: str
    result: FileEditResult

    def commit(self, cancelled: Event | None = None) -> None:
        with file_write_transaction([self.path], cancelled=cancelled):
            current = read_edit_snapshot(self.path) if self.path.exists() else None
            if current != self.before:
                raise ValueError(
                    f"File changed while preparing the edit: {self.path}. Read it again before editing."
                )
            atomic_write_text(self.path, self.after)
