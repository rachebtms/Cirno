"""Hash answer signatures without assembling full answers or their JSON encoding."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator

_CHUNK_CHARS = 8192


def _escaped_chunks(text: str) -> Iterator[bytes]:
    for offset in range(0, len(text), _CHUNK_CHARS):
        yield json.dumps(text[offset : offset + _CHUNK_CHARS], ensure_ascii=False)[1:-1].encode("utf-8")


def assistant_signature_identity(signature: Iterable[str]) -> str:
    """Match the JSON-array identity used by canonical recovery signatures."""
    digest = hashlib.sha256(b"[")
    count = 0
    for text in signature:
        if count:
            digest.update(b", ")
        digest.update(b'"')
        for chunk in _escaped_chunks(text):
            digest.update(chunk)
        digest.update(b'"')
        count += 1
    digest.update(b"]")
    return digest.hexdigest() if count else ""


class AnswerDigest:
    """Retain one hash state and a short preview across arbitrarily long streams."""

    def __init__(self) -> None:
        self._completed = hashlib.sha256(b"[")
        self._count = 0
        self.first_preview = ""
        self._reset()

    def _reset(self) -> None:
        self._active = self._completed.copy()
        if self._count:
            self._active.update(b", ")
        self._active.update(b'"')
        self._last_text = self._active.copy()
        self._started = False
        self._has_text = False
        self._preview = ""
        self._last_preview = ""

    def _append_preview(self, text: str) -> None:
        self._preview += text[: max(0, 240 - len(self._preview))]

    def _update(self, text: str) -> None:
        for chunk in _escaped_chunks(text):
            self._active.update(chunk)
        self._append_preview(text)

    def append(self, text: str) -> None:
        for offset in range(0, len(text), _CHUNK_CHARS):
            part = text[offset : offset + _CHUNK_CHARS]
            if not self._started:
                part = part.lstrip()
                if not part:
                    continue
                self._started = True
            core = part.rstrip()
            self._update(core)
            if core:
                self._has_text = True
                self._last_text = self._active.copy()
                self._last_preview = self._preview
            self._update(part[len(core) :])

    def replace(self, text: str) -> None:
        self._reset()
        self.append(text)

    def finish(self) -> None:
        if self._has_text:
            self._last_text.update(b'"')
            self._completed = self._last_text
            if not self._count:
                self.first_preview = self._last_preview
            self._count += 1
        self._reset()

    def identity(self) -> str:
        digest = self._completed.copy()
        digest.update(b"]")
        return digest.hexdigest() if self._count else ""
