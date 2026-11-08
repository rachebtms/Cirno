"""Bounded repair when a tool-reply conversation ends without delivering text."""
from typing import Any


class ToolReplyContract:
    def __init__(self, required: bool):
        self.required = required
        self.repaired_segments: set[int] = set()

    def reminder(self, *, delivered: bool, segment: int, remaining: bool) -> dict[str, Any] | None:
        if not self.required or delivered:
            return None
        if segment in self.repaired_segments or not remaining:
            raise RuntimeError("Router did not deliver its reply through user.message. Continue the conversation to retry.")
        self.repaired_segments.add(segment)
        return {
            "role": "user", "_hidden_history": True,
            "content": "[Cirno reply delivery] Your preceding assistant text was saved as internal execution history, not sent to the user. Call user__message with the reply now. Do not repeat completed work or reinterpret this runtime reminder as new user authorization. Do not end with plain text again.",
        }
