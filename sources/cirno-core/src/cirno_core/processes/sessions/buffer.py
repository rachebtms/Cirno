"""Bounded retained output shared by stream capture and observers."""

from collections import deque


class BoundedOutputBuffer:
    """Keep the first and most recent characters within a fixed budget."""

    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars
        self._content = ""
        self._tail: deque[str] = deque()
        self._tail_chars = 0
        self._total_chars = 0
        self._truncated = False

    @property
    def has_output(self) -> bool:
        return self._total_chars > 0

    @property
    def retained_chars(self) -> int:
        return len(self._content) + self._tail_chars

    def append(self, text: str) -> None:
        if not text:
            return
        self._total_chars += len(text)
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
            return

        tail_chars = self.max_chars - len(self._content)
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
        output = self._content + "".join(self._tail)
        truncated_chars = self._total_chars - len(output)
        self._content = ""
        self._tail.clear()
        self._tail_chars = 0
        self._total_chars = 0
        self._truncated = False
        return output, truncated_chars


def truncate_output(output: str, max_output_chars: int) -> tuple[str, int]:
    if len(output) <= max_output_chars:
        return output, 0
    head_chars = max_output_chars // 2
    tail_chars = max_output_chars - head_chars
    omitted = len(output) - max_output_chars
    return output[:head_chars] + output[-tail_chars:], omitted
