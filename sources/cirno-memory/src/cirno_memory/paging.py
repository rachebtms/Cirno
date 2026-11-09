"""Read bounded source pages without materializing an entire JSONL message."""

from collections.abc import Iterator
from typing import TextIO

PAGE_CHARS = 16_000


def source_chunks(stream: TextIO) -> Iterator[tuple[int, str]]:
    """Index long JSONL lines with bounded reads and a same-line overlap."""
    line, overlap = 1, ""
    while part := stream.readline(1400):
        yield line, overlap + part
        overlap = part[-100:] if not part.endswith("\n") else ""
        if part.endswith("\n"):
            line += 1


def source_page(stream: TextIO, *, start_line: int, limit: int, char_offset: int) -> dict:
    line_number = 1
    start_line, char_offset = max(1, start_line), max(0, char_offset)
    while line_number < start_line:
        chunk = stream.readline(PAGE_CHARS)
        if not chunk:
            return {"lines": [], "next_line": None}
        if chunk.endswith("\n"):
            line_number += 1
    lines, remaining = [], PAGE_CHARS
    for _ in range(max(1, min(limit, 20))):
        skipped, ended = 0, False
        while skipped < char_offset:
            chunk = stream.readline(min(PAGE_CHARS, char_offset - skipped))
            skipped += len(chunk)
            if not chunk or chunk.endswith("\n"):
                ended = True
                break
        part = "" if ended else stream.readline(remaining + 1)
        if not part and not skipped:
            break
        text = part[:remaining]
        continued = len(part) > remaining
        lines.append({"line": line_number, "text": text, "char_offset": char_offset,
                      "next_char_offset": char_offset + len(text) if continued else None})
        remaining -= len(text)
        if continued:
            return {"lines": lines, "next_line": None}
        line_number += 1
        char_offset = 0
        if not remaining:
            break
    return {"lines": lines, "next_line": line_number if stream.read(1) else None}
