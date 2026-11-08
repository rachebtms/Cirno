"""Bedrock responses conversion."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, cast

from cirno_usage.types import LLMUsage
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest, parse_tool_arguments


def finish_reason(stop_reason: str | None) -> str:
    return {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
    }.get(stop_reason or "", stop_reason or "stop")


def usage(usage: dict[str, Any] | None) -> LLMUsage | None:
    if not usage:
        return None

    def _optional_count(key: str) -> int | None:
        raw = usage.get(key)
        return int(raw) if raw is not None else None

    cache_read = _optional_count("cacheReadInputTokens")
    cache_write = _optional_count("cacheWriteInputTokens")
    logical_input = int(usage.get("inputTokens") or 0) + (cache_read or 0) + (cache_write or 0)
    return LLMUsage.reported(
        input_tokens=logical_input,
        output_tokens=int(usage.get("outputTokens") or 0),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )


def parse_reasoning(block: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    reasoning = block.get("reasoningContent")
    if not isinstance(reasoning, dict):
        return None, None
    reasoning = cast(dict[str, Any], reasoning)
    text_obj = reasoning.get("reasoningText")
    if isinstance(text_obj, dict):
        text_obj = cast(dict[str, Any], text_obj)
        text = text_obj.get("text")
        if isinstance(text, str):
            return text, {
                "type": "thinking",
                "thinking": text,
                "signature": text_obj.get("signature", ""),
            }
    redacted = reasoning.get("redactedContent")
    if redacted is not None:
        if isinstance(redacted, (bytes, bytearray)):
            encoded = base64.b64encode(bytes(redacted)).decode("ascii")
            return None, {"type": "redacted_thinking", "redactedContentBase64": encoded}
        return None, {"type": "redacted_thinking", "redactedContent": redacted}
    return None, None


def parse_response(response: dict[str, Any]) -> LLMResponse:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCallRequest] = []
    thinking_blocks: list[dict[str, Any]] = []
    output = cast(dict[str, Any], response.get("output") or {})
    message = cast(dict[str, Any], output.get("message") or {})

    content_blocks = cast(list[object], message.get("content") or [])
    for block_value in content_blocks:
        if not isinstance(block_value, dict):
            continue
        block = cast(dict[str, Any], block_value)
        if isinstance(block.get("text"), str):
            content_parts.append(cast(str, block["text"]))
        tool_use = block.get("toolUse")
        if isinstance(tool_use, dict):
            tool_use = cast(dict[str, Any], tool_use)
            arguments = tool_use.get("input", {})
            tool_calls.append(
                ToolCallRequest(
                    id=str(tool_use.get("toolUseId") or ""),
                    name=str(tool_use.get("name") or ""),
                    arguments=arguments,
                )
            )
        reasoning_text, thinking = parse_reasoning(block)
        if reasoning_text:
            reasoning_parts.append(reasoning_text)
        if thinking:
            thinking_blocks.append(thinking)

    return LLMResponse(
        content="".join(content_parts) or None,
        tool_calls=tool_calls,
        finish_reason=finish_reason(cast(str | None, response.get("stopReason"))),
        usage=usage(cast(dict[str, Any] | None, response.get("usage"))),
        reasoning_content="".join(reasoning_parts) or None,
        thinking_blocks=thinking_blocks or None,
    )


@dataclass(frozen=True)
class StreamDelta:
    text: str | None = None
    thinking: str | None = None
    tool: dict[str, Any] | None = None


def parse_stream_event(
    event: dict[str, Any],
    *,
    content_parts: list[str],
    reasoning_parts: list[str],
    thinking_blocks: list[dict[str, Any]],
    tool_buffers: dict[int, dict[str, Any]],
    state: dict[str, Any],
) -> StreamDelta | None:
    if "contentBlockStart" in event:
        data = cast(dict[str, Any], event["contentBlockStart"])
        idx = int(data.get("contentBlockIndex") or 0)
        start = cast(dict[str, Any], data.get("start") or {})
        tool_use = start.get("toolUse")
        if isinstance(tool_use, dict):
            tool_use = cast(dict[str, Any], tool_use)
            tool_buffers[idx] = {
                "id": str(tool_use.get("toolUseId") or ""),
                "name": str(tool_use.get("name") or ""),
                "input": "",
            }
            return StreamDelta(
                tool={
                    "index": idx,
                    "call_id": tool_buffers[idx]["id"],
                    "name": tool_buffers[idx]["name"],
                    "arguments_delta": "",
                }
            )
        return None

    if "contentBlockDelta" in event:
        data = cast(dict[str, Any], event["contentBlockDelta"])
        idx = int(data.get("contentBlockIndex") or 0)
        delta = cast(dict[str, Any], data.get("delta") or {})
        text = delta.get("text")
        if isinstance(text, str):
            content_parts.append(text)
            return StreamDelta(text=text)
        tool_delta = delta.get("toolUse")
        if isinstance(tool_delta, dict):
            tool_delta = cast(dict[str, Any], tool_delta)
            buf = tool_buffers.setdefault(idx, {"id": "", "name": "", "input": ""})
            if isinstance(tool_delta.get("input"), str):
                buf["input"] += tool_delta["input"]
                return StreamDelta(
                    tool={
                        "index": idx,
                        "call_id": buf["id"],
                        "name": buf["name"],
                        "arguments_delta": tool_delta["input"],
                    }
                )
        reasoning = delta.get("reasoningContent")
        if isinstance(reasoning, dict):
            reasoning = cast(dict[str, Any], reasoning)
            reasoning_buffers = cast(
                dict[int, dict[str, Any]],
                state.setdefault("reasoning_buffers", {}),
            )
            buf = reasoning_buffers.setdefault(
                idx, {"text": "", "signature": "", "redactedContent": None}
            )
            if isinstance(reasoning.get("text"), str):
                buf["text"] += reasoning["text"]
                reasoning_parts.append(reasoning["text"])
            if isinstance(reasoning.get("signature"), str):
                buf["signature"] = reasoning["signature"]
            if reasoning.get("redactedContent") is not None:
                buf["redactedContent"] = reasoning["redactedContent"]
            return StreamDelta(thinking=reasoning.get("text"))
        return None

    if "contentBlockStop" in event:
        stop = cast(dict[str, Any], event["contentBlockStop"] or {})
        idx = int(stop.get("contentBlockIndex") or 0)
        reasoning_buffers = cast(
            dict[int, dict[str, Any]],
            state.setdefault("reasoning_buffers", {}),
        )
        reasoning_buf = reasoning_buffers.pop(idx, None)
        if reasoning_buf:
            if reasoning_buf.get("text"):
                thinking_blocks.append(
                    {
                        "type": "thinking",
                        "thinking": reasoning_buf["text"],
                        "signature": reasoning_buf.get("signature", ""),
                    }
                )
            elif reasoning_buf.get("redactedContent") is not None:
                redacted = reasoning_buf["redactedContent"]
                if isinstance(redacted, (bytes, bytearray)):
                    redacted_block = {
                        "type": "redacted_thinking",
                        "redactedContentBase64": base64.b64encode(bytes(redacted)).decode("ascii"),
                    }
                else:
                    redacted_block = {
                        "type": "redacted_thinking",
                        "redactedContent": redacted,
                    }
                thinking_blocks.append(
                    {
                        **redacted_block,
                    }
                )
        return None

    if "messageStop" in event:
        message_stop = cast(dict[str, Any], event["messageStop"] or {})
        state["stop_reason"] = message_stop.get("stopReason")
        return None

    if "metadata" in event:
        metadata = cast(dict[str, Any], event["metadata"] or {})
        if isinstance(metadata.get("usage"), dict):
            state["usage"] = metadata["usage"]
        return None

    return None


def stream_result(
    *,
    content_parts: list[str],
    reasoning_parts: list[str],
    thinking_blocks: list[dict[str, Any]],
    tool_buffers: dict[int, dict[str, Any]],
    state: dict[str, Any],
) -> LLMResponse:
    tool_calls: list[ToolCallRequest] = []
    for buf in tool_buffers.values():
        args: Any = {}
        if buf.get("input"):
            args = parse_tool_arguments(buf["input"])
        tool_calls.append(
            ToolCallRequest(
                id=buf.get("id") or "",
                name=buf.get("name") or "",
                arguments=args,
            )
        )
    return LLMResponse(
        content="".join(content_parts) or None,
        tool_calls=tool_calls,
        finish_reason=finish_reason(state.get("stop_reason")),
        usage=usage(state.get("usage")),
        reasoning_content="".join(reasoning_parts) or None,
        thinking_blocks=thinking_blocks or None,
    )
