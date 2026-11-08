"""Bedrock messages conversion."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, cast

from cirno_core.providers.tool_calls import tool_arguments_object_for_replay

_IMAGE_DATA_URL = re.compile(r"^data:image/([a-zA-Z0-9.+-]+);base64,(.*)$", re.DOTALL)
_TEXT_BLOCK_TYPES = {"text", "input_text", "output_text"}
_NOOP_TOOL_NAME = "cirno_noop"


def image_url_block(block: dict[str, Any]) -> dict[str, Any] | None:
    image_url = cast(dict[str, Any], block.get("image_url") or {})
    url = image_url.get("url", "")
    if not isinstance(url, str) or not url:
        return None
    match = _IMAGE_DATA_URL.match(url)
    if not match:
        return {"text": f"(image URL: {url})"}
    fmt = match.group(1).lower()
    if fmt == "jpg":
        fmt = "jpeg"
    try:
        data = base64.b64decode(match.group(2), validate=False)
    except Exception:
        return {"text": "(invalid image data)"}
    return {"image": {"format": fmt, "source": {"bytes": data}}}


def content_blocks(content: Any, *, for_tool_result: bool = False) -> list[dict[str, Any]]:
    if isinstance(content, str) or content is None:
        return [{"text": content or "(empty)"}]
    if not isinstance(content, list):
        if for_tool_result and isinstance(content, dict):
            return [{"json": content}]
        return [{"text": str(content)}]

    blocks: list[dict[str, Any]] = []
    for raw_item in cast(list[object], content):
        if not isinstance(raw_item, dict):
            blocks.append({"text": str(raw_item)})
            continue
        item = cast(dict[str, Any], raw_item)

        item_type = item.get("type")
        if item_type in _TEXT_BLOCK_TYPES or "text" in item:
            text = item.get("text")
            if text:
                blocks.append({"text": str(text)})
            continue
        if item_type == "image_url":
            converted = image_url_block(item)
            if converted:
                blocks.append(converted)
            continue

        # Preserve already-Bedrock-shaped content where possible.
        for key in ("text", "image", "document", "video", "json", "searchResult"):
            if key in item:
                blocks.append({key: item[key]})
                break
        else:
            blocks.append({"json": item} if for_tool_result else {"text": json.dumps(item)})

    return blocks or [{"text": "(empty)"}]


def system_blocks(content: Any) -> list[dict[str, Any]]:
    return [
        block
        for block in content_blocks(content)
        if "text" in block or "cachePoint" in block or "guardContent" in block
    ]


def tool_result_block(msg: dict[str, Any]) -> dict[str, Any]:
    return {
        "toolResult": {
            "toolUseId": str(msg.get("tool_call_id") or ""),
            "content": content_blocks(msg.get("content"), for_tool_result=True),
            "status": "success",
        }
    }


def tool_use_block(tool_call: dict[str, Any]) -> dict[str, Any] | None:
    function = tool_call.get("function")
    if not isinstance(function, dict):
        return None
    function = cast(dict[str, Any], function)
    args = tool_arguments_object_for_replay(function.get("arguments", {}))
    return {
        "toolUse": {
            "toolUseId": str(tool_call.get("id") or ""),
            "name": str(function.get("name") or ""),
            "input": args,
        }
    }


def reasoning_block(block: dict[str, Any]) -> dict[str, Any] | None:
    if block.get("type") not in {"thinking", "reasoning", "redacted_thinking"}:
        return None
    text = block.get("thinking") or block.get("text")
    signature = block.get("signature")
    if text and signature:
        return {
            "reasoningContent": {"reasoningText": {"text": str(text), "signature": str(signature)}}
        }
    redacted = block.get("redactedContent")
    if redacted is None and isinstance(block.get("redactedContentBase64"), str):
        try:
            redacted = base64.b64decode(block["redactedContentBase64"])
        except Exception:
            redacted = None
    if redacted is not None:
        return {"reasoningContent": {"redactedContent": redacted}}
    return None


def assistant_blocks(msg: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    thinking_values = cast(list[object], msg.get("thinking_blocks") or [])
    for thinking_value in thinking_values:
        if isinstance(thinking_value, dict):
            thinking = cast(dict[str, Any], thinking_value)
            reasoning = reasoning_block(thinking)
            if reasoning:
                blocks.append(reasoning)

    content = msg.get("content")
    if isinstance(content, str) and content:
        blocks.append({"text": content})
    elif isinstance(content, list):
        blocks.extend(block for block in content_blocks(content) if "text" in block)

    tool_call_values = cast(list[object], msg.get("tool_calls") or [])
    for tool_call_value in tool_call_values:
        if isinstance(tool_call_value, dict):
            tool_call = cast(dict[str, Any], tool_call_value)
            block = tool_use_block(tool_call)
            if block:
                blocks.append(block)

    return blocks or [{"text": ""}]


def has_tool_use(msg: dict[str, Any]) -> bool:
    content = msg.get("content")
    return isinstance(content, list) and any(
        isinstance(block, dict) and "toolUse" in block for block in cast(list[object], content)
    )


def merge_consecutive(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for msg in messages:
        if merged and merged[-1].get("role") == msg.get("role"):
            prev = merged[-1].setdefault("content", [])
            cur: Any = msg.get("content") or []
            if not isinstance(prev, list):
                prev = [{"text": str(prev)}]
                merged[-1]["content"] = prev
            else:
                prev = cast(list[Any], prev)
            if isinstance(cur, list):
                prev.extend(cast(list[Any], cur))
            else:
                prev.append({"text": str(cur)})
        else:
            merged.append(msg)

    last_popped: dict[str, Any] | None = None
    while merged and merged[-1].get("role") == "assistant":
        last_popped = merged.pop()
    if not merged and last_popped is not None and not has_tool_use(last_popped):
        merged.append(
            {"role": "user", "content": last_popped.get("content") or [{"text": "(empty)"}]}
        )
    if merged and merged[0].get("role") == "assistant" and not has_tool_use(merged[0]):
        merged.insert(0, {"role": "user", "content": [{"text": "(conversation continued)"}]})
    return merged


def convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    system: list[dict[str, Any]] = []
    converted: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            system.extend(system_blocks(content))
            continue
        if role == "tool":
            block = tool_result_block(msg)
            if converted and converted[-1].get("role") == "user":
                converted[-1].setdefault("content", []).append(block)
            else:
                converted.append({"role": "user", "content": [block]})
            continue
        if role == "assistant":
            converted.append({"role": "assistant", "content": assistant_blocks(msg)})
            continue
        if role == "user":
            converted.append({"role": "user", "content": content_blocks(content)})

    return system, merge_consecutive(converted)


def convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    result: list[dict[str, Any]] = []
    for tool in tools:
        function_value = tool.get("function")
        func = cast(dict[str, Any], function_value) if isinstance(function_value, dict) else tool
        name = str(func.get("name") or "")
        if not name:
            continue
        spec: dict[str, Any] = {
            "name": name,
            "inputSchema": {"json": func.get("parameters") or {"type": "object", "properties": {}}},
        }
        description = func.get("description")
        if description:
            spec["description"] = str(description)
        strict = func.get("strict", tool.get("strict"))
        if isinstance(strict, bool):
            spec["strict"] = strict
        result.append({"toolSpec": spec})
    return result or None


def contains_tool_blocks(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block_value in cast(list[object], content):
            if isinstance(block_value, dict):
                block = cast(dict[str, Any], block_value)
                if "toolUse" in block or "toolResult" in block:
                    return True
    return False


def noop_tool() -> dict[str, Any]:
    return {
        "toolSpec": {
            "name": _NOOP_TOOL_NAME,
            "description": "Internal placeholder for Bedrock tool history validation.",
            "inputSchema": {"json": {"type": "object", "properties": {}}},
        }
    }


def convert_tool_choice(
    tool_choice: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if tool_choice is None or tool_choice == "auto":
        return {"auto": {}}
    if tool_choice == "required":
        return {"any": {}}
    if tool_choice == "none":
        return None
    if isinstance(tool_choice, dict):
        function = cast(dict[str, Any], tool_choice.get("function", {}))
        name = function.get("name")
        if name:
            return {"tool": {"name": str(name)}}
    return {"auto": {}}
