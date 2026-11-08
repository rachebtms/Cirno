"""Filesystem matching behavior and its owned helpers."""

# pyright: reportPrivateUsage=false

import difflib
import re
from array import array
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain

_QUOTE_TABLE = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",  # curly single → straight
        "\u201c": '"',
        "\u201d": '"',  # curly double → straight
        "'": "'",
        '"': '"',  # identity (kept for completeness)
    }
)


def _normalize_quotes(s: str) -> str:
    return s.translate(_QUOTE_TABLE)


def _curly_double_quotes(text: str) -> str:
    parts: list[str] = []
    opening = True
    for ch in text:
        if ch == '"':
            parts.append("\u201c" if opening else "\u201d")
            opening = not opening
        else:
            parts.append(ch)
    return "".join(parts)


def _curly_single_quotes(text: str) -> str:
    parts: list[str] = []
    opening = True
    for i, ch in enumerate(text):
        if ch != "'":
            parts.append(ch)
            continue
        prev_ch = text[i - 1] if i > 0 else ""
        next_ch = text[i + 1] if i + 1 < len(text) else ""
        if prev_ch.isalnum() and next_ch.isalnum():
            parts.append("\u2019")
            continue
        parts.append("\u2018" if opening else "\u2019")
        opening = not opening
    return "".join(parts)


def _preserve_quote_style(old_text: str, actual_text: str, new_text: str) -> str:
    """Preserve curly quote style when a quote-normalized fallback matched."""
    if (
        _normalize_quotes(old_text.strip()) != _normalize_quotes(actual_text.strip())
        or old_text == actual_text
    ):
        return new_text

    styled = new_text
    if any(ch in actual_text for ch in ("\u201c", "\u201d")) and '"' in styled:
        styled = _curly_double_quotes(styled)
    if any(ch in actual_text for ch in ("\u2018", "\u2019")) and "'" in styled:
        styled = _curly_single_quotes(styled)
    return styled


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _reindent_like_match(old_text: str, actual_text: str, new_text: str) -> str:
    """Preserve the outer indentation from the actual matched block."""
    # A terminal newline does not add a logical line, even at an unterminated EOF.
    old_lines = old_text.removesuffix("\n").split("\n")
    actual_lines = actual_text.removesuffix("\n").split("\n")
    if len(old_lines) != len(actual_lines):
        return new_text

    comparable = [
        (old_line, actual_line)
        for old_line, actual_line in zip(old_lines, actual_lines)
        if old_line.strip() and actual_line.strip()
    ]
    if not comparable or any(
        _normalize_quotes(old_line.strip()) != _normalize_quotes(actual_line.strip())
        for old_line, actual_line in comparable
    ):
        return new_text

    old_ws = _leading_ws(comparable[0][0])
    actual_ws = _leading_ws(comparable[0][1])
    if actual_ws == old_ws:
        return new_text

    if old_ws:
        if not actual_ws.startswith(old_ws):
            return new_text
        delta = actual_ws[len(old_ws) :]
    else:
        delta = actual_ws

    if not delta:
        return new_text

    return "\n".join((delta + line) if line else line for line in new_text.split("\n"))


@dataclass(slots=True)
class _MatchSpan:
    start: int
    end: int
    text: str
    line: int


def _match_end_line(match: _MatchSpan) -> int:
    comparable = match.text[:-1] if match.text.endswith("\n") else match.text
    return match.line + comparable.count("\n")


def _match_covers_line(match: _MatchSpan, line: int) -> bool:
    return match.line <= line <= _match_end_line(match)


def _substring_matches(
    content: str, old_text: str, searchable: str, needle: str
) -> Iterator[_MatchSpan]:
    start, line = 0, 1
    while (index := searchable.find(needle, start)) >= 0:
        line += content.count("\n", start, index)
        end = index + len(old_text)
        yield _MatchSpan(index, end, content[index:end], line)
        line += content.count("\n", index, end)
        start = end


def _find_exact_matches(content: str, old_text: str) -> Iterator[_MatchSpan]:
    return _substring_matches(content, old_text, content, old_text)


_LINE_BREAK = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")


def _line_ranges(content: str) -> Iterator[tuple[int, int]]:
    start = 0
    for match in _LINE_BREAK.finditer(content):
        yield start, match.end()
        start = match.end()
    if start < len(content):
        yield start, len(content)


def _find_trim_matches(
    content: str, old_text: str, *, normalize_quotes: bool = False
) -> Iterator[_MatchSpan]:
    def comparable(text: str) -> str:
        trimmed = text.strip()
        return _normalize_quotes(trimmed) if normalize_quotes else trimmed

    pattern = [comparable(line) for line in old_text.splitlines()]
    if not pattern:
        return
    # KMP avoids rescanning every overlapping line window in long files.
    fallback = array("I", [0]) * len(pattern)
    prefix = 0
    for index in range(1, len(pattern)):
        while prefix and pattern[index] != pattern[prefix]:
            prefix = fallback[prefix - 1]
        if pattern[index] == pattern[prefix]:
            prefix += 1
        fallback[index] = prefix

    starts: deque[int] = deque(maxlen=len(pattern))
    matched = 0
    for line, (start, end) in enumerate(_line_ranges(content), 1):
        starts.append(start)
        value = comparable(content[start:end])
        while matched and value != pattern[matched]:
            matched = fallback[matched - 1]
        if value == pattern[matched]:
            matched += 1
        if matched == len(pattern):
            match_end = end
            if not old_text.endswith("\n") and content[end - 1] == "\n":
                match_end -= 1
            yield _MatchSpan(
                starts[0], match_end, content[starts[0] : match_end], line - len(pattern) + 1
            )
            matched = fallback[matched - 1]


def _find_quote_matches(content: str, old_text: str) -> Iterator[_MatchSpan]:
    return _substring_matches(
        content, old_text, _normalize_quotes(content), _normalize_quotes(old_text)
    )


def _find_matches(content: str, old_text: str) -> Iterator[_MatchSpan]:
    """Locate all matches using progressively looser strategies."""
    for matcher in (
        lambda: _find_exact_matches(content, old_text),
        lambda: _find_trim_matches(content, old_text),
        lambda: _find_trim_matches(content, old_text, normalize_quotes=True),
        lambda: _find_quote_matches(content, old_text),
    ):
        matches = matcher()
        first = next(matches, None)
        if first is not None:
            return chain((first,), matches)
    return iter(())


def _collapse_internal_whitespace(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def _diagnose_near_match(old_text: str, actual_text: str) -> list[str]:
    """Return actionable hints describing why text was close but not exact."""
    hints: list[str] = []

    if old_text.lower() == actual_text.lower() and old_text != actual_text:
        hints.append("letter case differs")
    if (
        _collapse_internal_whitespace(old_text) == _collapse_internal_whitespace(actual_text)
        and old_text != actual_text
    ):
        hints.append("whitespace differs")
    if old_text.rstrip("\n") == actual_text.rstrip("\n") and old_text != actual_text:
        hints.append("trailing newline differs")
    if _normalize_quotes(old_text) == _normalize_quotes(actual_text) and old_text != actual_text:
        hints.append("quote style differs")

    return hints


def _best_window(old_text: str, content: str) -> tuple[float, int, list[str], list[str]]:
    """Find the closest line-window match and return ratio/start/snippet/hints."""
    lines = content.splitlines(keepends=True)
    old_lines = old_text.splitlines(keepends=True)
    window = max(1, len(old_lines))

    best_ratio, best_start = -1.0, 0
    best_window_lines: list[str] = []

    for i in range(max(1, len(lines) - window + 1)):
        current = lines[i : i + window]
        ratio = difflib.SequenceMatcher(None, old_lines, current).ratio()
        if ratio > best_ratio:
            best_ratio, best_start = ratio, i
            best_window_lines = current

    actual_text = "".join(best_window_lines).replace("\r\n", "\n").rstrip("\n")
    hints = _diagnose_near_match(old_text.replace("\r\n", "\n").rstrip("\n"), actual_text)
    return best_ratio, best_start, best_window_lines, hints
