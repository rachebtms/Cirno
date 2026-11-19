"""Bounded retained output shared by stream capture and observers."""

from collections import deque


def _trim_gaps(gaps: set[int], head: int, tail_start: int) -> set[int]:
    """Keep discontinuities outside a removed middle range, plus that range."""
    return {head} | {gap for gap in gaps if gap <= head} | {
        gap - (tail_start - head) for gap in gaps if gap >= tail_start
    }


class BoundedOutputBuffer:
    """Keep the first and most recent characters within a fixed budget."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars
        self._content = ""
        self._tail: deque[str] = deque()
        self._tail_chars = 0
        self._total_chars = 0
        self._truncated = False
        self._gaps: set[int] = set()

    @property
    def has_output(self) -> bool:
        return self._total_chars > 0

    @property
    def retained_chars(self) -> int:
        return len(self._content) + self._tail_chars

    def append(self, text: str, *, gaps: tuple[int, ...] = ()) -> None:
        size = self.retained_chars
        self._gaps.update(size + gap for gap in gaps)
        if not text:
            return
        self._total_chars += len(text)
        if self.max_chars == 0:
            self._gaps = {0}
            return
        if not self._truncated:
            combined = self._content + text
            if len(combined) <= self.max_chars:
                self._content = combined
                return
            head_chars = self.max_chars // 2
            tail_chars = self.max_chars - head_chars
            self._content = combined[:head_chars]
            self._tail.append(combined[-tail_chars:])
            self._tail_chars = tail_chars
            self._truncated = True
            self._gaps = _trim_gaps(self._gaps, head_chars, len(combined) - tail_chars)
            return

        tail_chars = self.max_chars - len(self._content)
        self._gaps = _trim_gaps(self._gaps, len(self._content), size + len(text) - tail_chars)
        self._tail.append(text)
        self._tail_chars += len(text)
        while self._tail_chars > tail_chars:
            excess = self._tail_chars - tail_chars
            first = self._tail[0]
            if len(first) <= excess:
                self._tail.popleft()
                self._tail_chars -= len(first)
            else:
                self._tail[0] = first[excess:]
                self._tail_chars -= excess

    def drain(self) -> tuple[str, int]:
        output, truncated, _gaps = self.drain_with_gaps()
        return output, truncated

    def drain_with_gaps(self) -> tuple[str, int, tuple[int, ...]]:
        output = self._content + "".join(self._tail)
        truncated_chars = self._total_chars - len(output)
        gaps = tuple(sorted(self._gaps))
        self._content = ""
        self._tail.clear()
        self._tail_chars = 0
        self._total_chars = 0
        self._truncated = False
        self._gaps.clear()
        return output, truncated_chars, gaps


def truncate_output(output: str, max_output_chars: int) -> tuple[str, int]:
    text, truncated, _gaps = truncate_output_with_gaps(output, max_output_chars)
    return text, truncated


def truncate_output_with_gaps(
    output: str, max_output_chars: int, gaps: tuple[int, ...] = (),
) -> tuple[str, int, tuple[int, ...]]:
    if len(output) <= max_output_chars:
        return output, 0, gaps
    if max_output_chars == 0:
        return "", len(output), (0,)
    head_chars = max_output_chars // 2
    tail_chars = max_output_chars - head_chars
    omitted = len(output) - max_output_chars
    retained_gaps = _trim_gaps(set(gaps), head_chars, len(output) - tail_chars)
    return output[:head_chars] + output[-tail_chars:], omitted, tuple(sorted(retained_gaps))
