"""Visit answer boundaries consistently for recovery and lightweight indexes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def visit_transcript_answers(
    records: Iterable[dict[str, Any]],
    append: Callable[[str], None],
    replace: Callable[[str], None],
    finish: Callable[[], None],
) -> None:
    for record in records:
        event = record.get("event")
        text = record.get("text")
        if event == "delta":
            if isinstance(text, str):
                append(text)
        elif event == "stream_end":
            if isinstance(text, str):
                replace(text)
            if record.get("resuming") is True and record.get("merge_next") is True:
                continue
            finish()
        elif event == "message" and record.get("kind") not in {"tool_hint", "progress", "reasoning"}:
            finish()
            if isinstance(text, str):
                append(text)
                finish()
        elif event in {"user", "reasoning_delta", "reasoning_end", "turn_end"}:
            finish()
    finish()
