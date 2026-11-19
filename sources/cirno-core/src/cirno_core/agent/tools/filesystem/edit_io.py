"""Shared bounded snapshots for edits that retain originals and calculate diffs."""

from array import array
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from cirno_core.utils.atomic_file import atomic_write_text, read_atomic_bytes
from cirno_core.utils.file_edit_events import FileEditResult
from cirno_core.utils.file_transactions import file_write_transaction

MAX_EDIT_BYTES = 2 * 1024 * 1024
MAX_PATCH_BYTES = 8 * 1024 * 1024


def publish_file_text(path: Path, content: str) -> None:
    """An atomic publisher can fail after rename; don't imply no write occurred."""
    try:
        atomic_write_text(path, content)
    except Exception as exc:
        raise OSError(
            f"Write outcome unconfirmed for {path}; contents may already have changed. "
            f"Read it before retrying. Persistence error: {exc}"
        ) from exc


class EditText:
    """Match normalized newlines while copying untouched original text exactly."""

    def __init__(self, original: str) -> None:
        self.original = original
        self.text = original.replace("\r\n", "\n")
        self._crlf = array("I")
        offset = 0
        while (offset := original.find("\r\n", offset)) >= 0:
            self._crlf.append(offset - len(self._crlf))
            offset += 2
        self._line_start = self._line_end = -1
        self._ending = "\n"

    def original_offset(self, offset: int) -> int:
        return offset + bisect_left(self._crlf, offset)

    def slice(self, start: int, end: int | None = None) -> str:
        return self.original[
            self.original_offset(start) : self.original_offset(end) if end is not None else None
        ]

    def line_ending(self, offset: int) -> str:
        if not self._line_start <= offset <= self._line_end:
            following = self.text.find("\n", offset)
            previous = self.text.rfind("\n", 0, offset)
            newline = following if following >= 0 else previous
            self._line_start = previous + 1
            self._line_end = following if following >= 0 else len(self.text)
            self._ending = (
                "\r\n"
                if newline >= 0 and self.original[self.original_offset(newline)] == "\r"
                else "\n"
            )
        return self._ending

    def replacement(self, text: str, start: int) -> str:
        return text.replace("\r\n", "\n").replace("\n", self.line_ending(start))


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
            publish_file_text(self.path, self.after)
