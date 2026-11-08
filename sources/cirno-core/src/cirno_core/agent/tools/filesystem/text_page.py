"""Bounded text pagination: scan and hash the file without retaining its corpus."""

from __future__ import annotations

import codecs
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from cirno_core.utils.atomic_file import open_atomic_snapshot

_LINE_END = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
_BREAK_CHARACTERS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")


@dataclass(frozen=True)
class TextPage:
    text: str
    content_hash: str
    total_lines: int
    end_line: int
    truncated_line: bool


class _PageCollector:
    def __init__(self, offset: int, limit: int, max_chars: int):
        self.offset, self.limit, self.max_chars = offset, limit, max_chars
        self.line = 1
        self.line_chars = 0
        self.fragments: list[str] = []
        self.captured = 0
        self.rows: list[str] = []
        self.used = 0
        self.end_line = 0
        self.truncated = False
        self.done = False
        self.has_tail = False
        self.previous_cr = False

    def _fragment(self, text: str) -> None:
        if not text:
            return
        self.has_tail = True
        if self.line >= self.offset and not self.done:
            self.line_chars += len(text)
            remaining = self.max_chars - self.captured
            if remaining > 0:
                self.fragments.append(text[:remaining])
                self.captured += min(len(text), remaining)

    def _end_line(self) -> None:
        if self.line >= self.offset and not self.done:
            prefix = f"{self.line}| "
            width = len(prefix) + self.line_chars + bool(self.rows)
            if self.used + width <= self.max_chars:
                self.rows.append(prefix + "".join(self.fragments))
                self.used += width
                self.end_line = self.line
            elif not self.rows:
                self.rows.append(
                    prefix + "".join(self.fragments)[: max(0, self.max_chars - len(prefix))]
                )
                self.truncated = True
                self.end_line = self.line
                self.done = True
            else:
                self.done = True
            if len(self.rows) == self.limit:
                self.done = True
        self.fragments.clear()
        self.captured, self.line_chars, self.has_tail = 0, 0, False
        self.line += 1

    def accept(self, text: str) -> None:
        if not text:
            return
        if self.previous_cr and text.startswith("\n"):
            text = text[1:]
        if not text:
            self.previous_cr = False
            return
        self.previous_cr = text.endswith("\r")
        # Once the page is settled, only count separators; no line objects survive.
        breaks = _LINE_END.findall(text)
        if self.done or self.line + len(breaks) < self.offset:
            self.line += len(breaks)
            self.has_tail = text[-1] not in _BREAK_CHARACTERS
            return
        start = 0
        for match in _LINE_END.finditer(text):
            self._fragment(text[start : match.start()])
            self._end_line()
            start = match.end()
        self._fragment(text[start:])

    def finish(self, digest: str) -> TextPage:
        if self.has_tail:
            self._end_line()
        return TextPage("\n".join(self.rows), digest, self.line - 1, self.end_line, self.truncated)


def read_text_page(
    path: Path,
    *,
    encoding: str,
    offset: int,
    limit: int,
    max_chars: int,
    max_bytes: int,
    cancelled: Event,
) -> TextPage:
    collector = _PageCollector(offset, limit, max_chars)
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    digest = hashlib.sha256()
    scanned = 0
    with open_atomic_snapshot(path) as source:
        while chunk := source.read(64 * 1024):
            if cancelled.is_set():
                raise InterruptedError("File read cancelled")
            scanned += len(chunk)
            if scanned > max_bytes:
                raise ValueError("File grew beyond the read limit; select a smaller file")
            digest.update(chunk)
            collector.accept(decoder.decode(chunk))
        collector.accept(decoder.decode(b"", final=True))
    return collector.finish(digest.hexdigest())


def text_encoding(header: bytes) -> str:
    if header.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        return "utf-32"
    if header.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"
    return "utf-8-sig"
