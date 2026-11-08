"""Read bounded UTF-8 text or a located document line stream."""

from pathlib import Path

from cirno_core.utils.document import (
    DocumentLineSource,
    LocatedDocumentLine,
    open_document_line_source,
)

DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx", ".pptx"})


def _is_binary(raw: bytes) -> bool:
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    if not sample:
        return False
    non_text = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return (non_text / len(sample)) > 0.2


def open_source(path: Path, pages: str | None, max_bytes: int) -> DocumentLineSource | None:
    if path.suffix.lower() in DOCUMENT_EXTENSIONS:
        return open_document_line_source(path, pages=pages)
    with path.open("rb") as file:
        raw = file.read(max_bytes + 1)
    if _is_binary(raw):
        return None
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return DocumentLineSource(
        LocatedDocumentLine(text, line_no, "")
        for line_no, text in enumerate(content.splitlines(), 1)
    )
