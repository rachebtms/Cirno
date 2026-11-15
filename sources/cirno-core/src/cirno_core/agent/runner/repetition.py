"""Incremental consecutive prose-block detection, independent of providers."""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any, cast

from cirno_core.agent.tools.naming import implementation_name
from cirno_core.config.repetition import OutputRepetitionConfig
from cirno_core.session.history_visibility import is_hidden_history_message

GUIDANCE_KIND = "repetition_guidance"
REPETITION_PAUSED_NOTICE = (
    "Repeated output interrupted; correction limit reached. Execution paused. "
    "Review the conversation before continuing."
)
_SEPARATORS = frozenset("\n。！？.!?")
_MAX_BLOCK_CHARS = 8192


class RepeatedOutputDetected(asyncio.CancelledError):
    """Close the provider stream without its network-error retry machinery."""


class RepeatedBlocks:
    """Count equal adjacent sentences/lines; fenced code is excluded."""

    def __init__(self, threshold: int):
        self.threshold = threshold
        self.pending = ""
        self.last = ""
        self.count = 0
        self.fence: str | None = None
        self.overlong = False

    def _block(self) -> bool:
        text, self.pending = self.pending, ""
        stripped = text.strip()
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            self.fence = None if self.fence == fence else fence
            self.last, self.count = "", 0
            return False
        if self.fence or self.overlong:
            self.overlong = False
            self.last, self.count = "", 0
            return False
        text = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", text)
        normalized = " ".join(unicodedata.normalize("NFKC", text).split()).casefold()
        normalized = normalized.strip(" 。！？.!?")
        if sum(char.isalnum() for char in normalized) < 2:
            return False
        self.count = self.count + 1 if normalized == self.last else 1
        self.last = normalized
        return self.count >= self.threshold

    def feed(self, text: str, *, final: bool = False, stop_on_repeat: bool = True) -> bool:
        repeated = False
        for char in text:
            # Keep fenced source intact until newline, even if it contains dots.
            if char in _SEPARATORS and (not self.fence or char == "\n"):
                if self._block():
                    repeated = True
                    if stop_on_repeat:
                        return True
            elif len(self.pending) < _MAX_BLOCK_CHARS:
                self.pending += char
            else:
                self.overlong = True
        return (self._block() if final else False) or repeated


def message_tool_text(name: str, arguments: Any) -> str | None:
    if implementation_name(name) != "message":
        return None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None  # The normal tool-argument validator owns malformed calls.
    if not isinstance(arguments, dict):
        return None
    content = cast(dict[str, Any], arguments).get("content")
    return content if isinstance(content, str) else None


class OutputRepetitionGuard:
    """Seed recent output across automatic turns, resetting at genuine input."""

    def __init__(self, config: OutputRepetitionConfig, messages: list[dict[str, Any]]):
        self.config = config
        self.content = RepeatedBlocks(config.repeat_count)
        self.reasoning = RepeatedBlocks(config.repeat_count)
        self.interventions = 0
        if not config.enabled:
            return
        # Only recent output matters; never repeatedly scan a long task's archive.
        for message in messages[-128:]:
            role = message.get("role")
            if role == "user" and not is_hidden_history_message(message):
                self.content = RepeatedBlocks(config.repeat_count)
                self.interventions = 0
            marker = message.get("_hidden_history")
            if isinstance(marker, dict) and cast(dict[str, Any], marker).get("kind") == GUIDANCE_KIND:
                self.interventions += 1
                self.content = RepeatedBlocks(config.repeat_count)
            if role != "assistant" or is_hidden_history_message(message):
                continue
            content = message.get("content")
            if isinstance(content, str):
                self.content.feed(content, final=True, stop_on_repeat=False)
            for call in cast(list[dict[str, Any]], message.get("tool_calls") or []):
                function = cast(dict[str, Any], call.get("function") or {})
                text = message_tool_text(function.get("name", ""), function.get("arguments"))
                if text:
                    self.content.feed(text, final=True, stop_on_repeat=False)

    def check(self, text: str, *, reasoning: bool = False, final: bool = False) -> None:
        if self.config.enabled and (self.reasoning if reasoning else self.content).feed(text, final=final):
            raise RepeatedOutputDetected()

    def stream_callbacks(self) -> dict[str, Callable[[str], Awaitable[None]]]:
        """Inspect streams even when live display is disabled or finalizing."""
        if not self.config.enabled:
            return {}
        async def content(delta: str) -> None:
            self.check(delta)
        async def reasoning(delta: str) -> None:
            self.check(delta, reasoning=True)
        return {"on_content_delta": content, "on_thinking_delta": reasoning}

    def guidance_message(self) -> dict[str, Any]:
        return {
            "role": "user", "_hidden_history": {"kind": GUIDANCE_KIND},
            "content": "[Agent system notice, not a new user request] " + self.config.guidance,
        }
