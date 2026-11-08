"""Model message framing, images and persisted media breadcrumbs."""

from __future__ import annotations

import base64
from typing import Any, cast

from cirno_core.utils.reasoning import strip_reasoning_tags


def detect_image_mime(data: bytes) -> str | None:
    """Detect image MIME type from magic bytes, ignoring file extension."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def build_image_content_blocks(
    raw: bytes, mime: str, path: str, label: str
) -> list[dict[str, Any]]:
    """Build native image blocks plus a short text label."""
    b64 = base64.b64encode(raw).decode()
    return [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
            "_meta": {"path": path},
        },
        {"type": "text", "text": label},
    ]


def image_placeholder_text(path: str | None, *, empty: str = "[image]") -> str:
    """Build an image placeholder string."""
    return f"[image: {path}]" if path else empty


def content_with_media_breadcrumbs(
    role: str | None,
    content: Any,
    media: Any,
) -> Any:
    """Append persisted user-media breadcrumbs to plain-text content."""
    if role != "user" or not isinstance(content, str) or not isinstance(media, list):
        return content
    breadcrumbs = "\n".join(
        image_placeholder_text(path)
        for path in cast(list[object], media)
        if isinstance(path, str) and path
    )
    if not breadcrumbs:
        return content
    return f"{content}\n{breadcrumbs}" if content else breadcrumbs


def recent_message_start_index(
    messages: list[dict[str, Any]],
    max_messages: int,
    *,
    extend_to_user: bool = False,
) -> int:
    """Return the start index for a recent replay window."""
    if max_messages <= 0:
        return len(messages)
    start_idx = max(0, len(messages) - max_messages)
    if not extend_to_user or len(messages) <= max_messages:
        return start_idx
    if any(messages[i].get("role") == "user" for i in range(start_idx, len(messages))):
        return start_idx

    recovered_user = next(
        (i for i in range(start_idx - 1, -1, -1) if messages[i].get("role") == "user"),
        None,
    )
    if recovered_user is None:
        return start_idx
    if recovered_user > 0 and messages[recovered_user - 1].get("_channel_delivery"):
        return recovered_user - 1
    return recovered_user


def find_legal_message_start(messages: list[dict[str, Any]]) -> int:
    """Find the first index whose tool results have matching assistant calls."""
    declared: set[str] = set()
    start = 0
    for i, msg in enumerate(messages):
        role = msg.get("role")
        if role == "assistant":
            for raw_call in cast(list[object], msg.get("tool_calls") or []):
                tool_call = cast(dict[str, Any], raw_call) if isinstance(raw_call, dict) else None
                if tool_call is not None and tool_call.get("id"):
                    declared.add(str(tool_call["id"]))
        elif role == "tool":
            tid = msg.get("tool_call_id")
            if tid and str(tid) not in declared:
                start = i + 1
                declared.clear()
    return start


def stringify_text_blocks(content: list[object]) -> str | None:
    parts: list[str] = []
    for raw_block in content:
        if not isinstance(raw_block, dict):
            return None
        block = cast(dict[str, Any], raw_block)
        if block.get("type") != "text":
            return None
        text = block.get("text")
        if not isinstance(text, str):
            return None
        parts.append(text)
    return "\n".join(parts)


def build_assistant_message(
    content: str | None,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning_content: str | None = None,
    thinking_blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a provider-safe assistant message with optional reasoning fields."""
    msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if reasoning_content is not None or thinking_blocks:
        msg["reasoning_content"] = (
            strip_reasoning_tags(reasoning_content) if reasoning_content is not None else ""
        )
    if thinking_blocks:
        msg["thinking_blocks"] = thinking_blocks
    return msg
