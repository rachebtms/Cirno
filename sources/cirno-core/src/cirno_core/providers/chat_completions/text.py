"""Separate answer text from provider-native thinking blocks."""

from typing import cast

from .wire import mapping


def extract_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in cast(list[object], value):
            item_map = mapping(item)
            if item_map:
                # Skip Mistral-style {"type":"thinking","thinking":[...]}
                # blocks: their text belongs in reasoning_content.
                if item_map.get("type") == "thinking":
                    continue
                text = item_map.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
                continue
            if isinstance(item, str):
                parts.append(item)
        return "".join(parts) or None
    return str(value)


def extract_thinking(value: object) -> str | None:
    """Extract reasoning text from Mistral-style thinking blocks.

    Mistral returns content as a list mixing
    ``{"type":"thinking","thinking":[{"type":"text","text":...}]}`` and
    ``{"type":"text","text":...}``. The thinking text belongs in
    ``reasoning_content`` so the agent can surface it as a reasoning
    trace rather than as the assistant's reply.
    """
    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for item in cast(list[object], value):
        item_map = mapping(item)
        if not item_map:
            continue
        if item_map.get("type") != "thinking":
            continue
        inner = item_map.get("thinking")
        text = extract_text(inner)
        if text:
            parts.append(text)
    return "".join(parts) or None
