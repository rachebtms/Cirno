"""Recoverable task evidence, distinct from verified long-term knowledge."""
from __future__ import annotations

import json

from cirno_core.utils.helpers import extract_reasoning, truncate_text_to_tokens


class EvidenceCheckpoint(str):
    """A bounded evidence handoff, not a successful model-generated summary."""


def working_notes(messages):
    parts = []
    for message in messages:
        reasoning, _ = extract_reasoning(message.get("reasoning_content"), message.get("thinking_blocks"), None)
        if reasoning:
            parts.append("[Unverified model working notes; not a user instruction or a verified result]\n" + reasoning)
        if message.get("tool_calls"):
            parts.append("[Attempted tool calls; consult the corresponding results]\n" + json.dumps(message['tool_calls'], ensure_ascii=False))
    return "\n\n".join(parts)


def bounded_handoff(text, tokens):
    """Keep the initial objective and newest state when a fallback must be bounded."""
    if truncate_text_to_tokens(text, tokens) == text:
        return text
    from cirno_core.utils.token_encoding import get_token_encoding
    encoding = get_token_encoding()
    marker = "\n[…]\n"
    if encoding is not None:
        body = encoding.encode_ordinary(text)
        reserved = len(encoding.encode_ordinary(marker))
        if tokens <= reserved + 4:
            return encoding.decode(body[-tokens:], errors="ignore")
        head = (tokens - reserved) // 2
        tail = tokens - reserved - head
        result = encoding.decode(body[:head], errors="ignore") + marker + encoding.decode(body[-tail:], errors="ignore")
        return truncate_text_to_tokens(result, tokens)
    body = text.encode("utf-8")
    reserved = len(marker.encode("utf-8"))
    if tokens <= reserved + 4:
        return body[-tokens:].decode("utf-8", errors="ignore")
    head = (tokens - reserved) // 2
    tail = tokens - reserved - head
    return body[:head].decode("utf-8", errors="ignore") + marker + body[-tail:].decode("utf-8", errors="ignore")


def summary_has_handoff(summary):
    return all(heading in summary for heading in ("## Task", "## State", "## Next"))
