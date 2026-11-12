"""Resolve exact archive quotes without making the model count a long transcript."""

from __future__ import annotations

from typing import Any

from cirno_core.memory.consolidation_contract import EvidenceRef
from cirno_core.runtime.context import public_history_message


class LearningEvidenceError(ValueError):
    """Generated citations failed before any learning effects were applied."""


def matches_quote(message: dict[str, Any], quote: str, *, user_only: bool) -> bool:
    content = (public_history_message(message) if user_only else message).get("content", "")
    if isinstance(content, str):
        return quote in content
    if isinstance(content, list):
        # Match actual text, including its newlines, rather than only JSON escapes.
        # Images and other block metadata cannot substantiate a textual finding.
        return any(
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
            and quote in block["text"]
            for block in content
        )
    return False


def resolve_message(messages: list[dict[str, Any]], ref: EvidenceRef, *, user_only=False) -> int:
    if ref.message is not None:
        if ref.message >= len(messages):
            raise LearningEvidenceError("Learning evidence message is outside the archived batch")
        if not matches_quote(messages[ref.message], ref.quote, user_only=user_only):
            raise LearningEvidenceError(
                f"Learning evidence quote does not match the archived message (index {ref.message}); "
                "copy an exact text quote, or omit message to locate a unique archive quote"
            )
        return ref.message
    matches = [
        i
        for i, message in enumerate(messages)
        if matches_quote(message, ref.quote, user_only=user_only)
    ]
    if len(matches) != 1:
        detail = (
            "does not match any archived message"
            if not matches
            else "matches multiple archived messages"
        )
        raise LearningEvidenceError(f"Learning evidence quote {detail}; use a unique exact quote")
    return matches[0]


def source_refs(messages: list[dict[str, Any]], refs: list[EvidenceRef]) -> list[dict[str, Any]]:
    return [
        ref.model_dump()
        if ref.memory_id is not None
        else ref.model_copy(update={"message": resolve_message(messages, ref)}).model_dump()
        for ref in refs
    ]


def needs_new_output(record: dict[str, Any]) -> bool:
    # Legacy quote errors also occurred in preflight, before writes. Storage and
    # concurrent-edit failures must keep their original plan for idempotent replay.
    return record.get("status") == "failed" and (
        record.get("regenerate_output") is True
        or record.get("error")
        in {
            "ValueError: Learning evidence quote does not match the archived message",
            "ValueError: Learning evidence quote does not match its memory",
            "ValueError: Learning evidence message is outside the archived batch",
        }
    )
