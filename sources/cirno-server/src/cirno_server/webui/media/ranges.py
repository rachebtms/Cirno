"""Single HTTP byte ranges shared by every signed attachment format."""

import re

_BYTE_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_byte_range(value: str, size: int) -> tuple[int, int]:
    match = _BYTE_RANGE_RE.fullmatch(value.strip())
    if size <= 0 or match is None:
        raise ValueError("range not satisfiable")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise ValueError("range not satisfiable")
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("range not satisfiable")
        return max(size - suffix, 0), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start >= size or start > end:
        raise ValueError("range not satisfiable")
    return start, min(end, size - 1)
