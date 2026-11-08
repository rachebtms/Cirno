"""Request token accounting and bounded tool-definition caches."""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from contextlib import suppress
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from tiktoken import Encoding

from cirno_core.utils import token_encoding
from cirno_core.utils.reasoning import extract_reasoning

_TOOLS_TOKEN_CACHE_MAX_ENTRIES = 64
_TOOLS_TOKEN_CACHE_MAX_BYTES = 1_048_576
_TOOLS_TOKEN_CACHE: OrderedDict[tuple[int, str], tuple[object, dict[bool, int]]] = OrderedDict()
_TOOLS_TOKEN_CACHE_LOCK = Lock()


def _estimate_tools_tokens(
    enc: Encoding,
    tools: list[dict[str, Any]],
    *,
    leading_separator: bool,
) -> int:
    """Cache encoded counts by schema content and the actual tokenizer instance."""
    rendered = json.dumps(tools, ensure_ascii=False)
    key = (id(enc), rendered)
    with _TOOLS_TOKEN_CACHE_LOCK:
        cached = _TOOLS_TOKEN_CACHE.get(key)
        if cached is not None:
            _TOOLS_TOKEN_CACHE.move_to_end(key)
            count = cached[1].get(leading_separator)
            if count is not None:
                return count
    count = len(enc.encode_ordinary(("\n" if leading_separator else "") + rendered))
    if sys.getsizeof(rendered) <= _TOOLS_TOKEN_CACHE_MAX_BYTES:
        with _TOOLS_TOKEN_CACHE_LOCK:
            cached = _TOOLS_TOKEN_CACHE.get(key)
            counts = dict(cached[1]) if cached is not None else {}
            counts[leading_separator] = count
            # Retaining the encoder also prevents identity reuse across vocabulary changes.
            _TOOLS_TOKEN_CACHE[key] = (enc, counts)
            _TOOLS_TOKEN_CACHE.move_to_end(key)
            while len(_TOOLS_TOKEN_CACHE) > _TOOLS_TOKEN_CACHE_MAX_ENTRIES or sum(
                sys.getsizeof(item[1]) for item in _TOOLS_TOKEN_CACHE
            ) > _TOOLS_TOKEN_CACHE_MAX_BYTES:
                _TOOLS_TOKEN_CACHE.popitem(last=False)
    return count


def _estimate_prompt_tokens_with_source(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[int, str]:
    """Estimate prompt tokens and identify the counter used.

    Counts all fields that providers send to the LLM: content, tool_calls,
    reasoning_content, tool_call_id, name, plus per-message framing overhead.
    """
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for raw_part in cast(list[object], content):
                part = cast(dict[str, Any], raw_part) if isinstance(raw_part, dict) else None
                if part is not None and part.get("type") == "text":
                    text = part.get("text", "")
                    if isinstance(text, str) and text:
                        parts.append(text)

        tc = msg.get("tool_calls")
        if tc:
            parts.append(json.dumps(tc, ensure_ascii=False))

        rc = (
            msg.get("reasoning_content")
            or extract_reasoning(None, msg.get("thinking_blocks"), None)[0]
        )
        if isinstance(rc, str) and rc:
            parts.append(rc)

        for key in ("name", "tool_call_id"):
            value = msg.get(key)
            if isinstance(value, str) and value:
                parts.append(value)

    message_payload = "\n".join(parts)
    per_message_overhead = len(messages) * 4
    try:
        enc = token_encoding.get_token_encoding()
        if enc is not None:
            tool_tokens = (
                _estimate_tools_tokens(enc, tools, leading_separator=bool(parts)) if tools else 0
            )
            message_tokens = len(enc.encode_ordinary(message_payload)) if message_payload else 0
            return message_tokens + tool_tokens + per_message_overhead, "tiktoken"
    except Exception:
        pass
    tool_payload = (
        ("\n" if message_payload else "") + json.dumps(tools, ensure_ascii=False) if tools else ""
    )
    payload = message_payload + tool_payload
    estimated = len(payload.encode("utf-8"))
    return estimated + per_message_overhead, "heuristic"


def estimate_prompt_tokens(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """Estimate prompt tokens with tiktoken and a conservative byte fallback."""
    estimated, _ = _estimate_prompt_tokens_with_source(messages, tools)
    return estimated


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """Estimate prompt tokens contributed by one persisted message."""
    content = message.get("content")
    parts: list[str] = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for raw_part in cast(list[object], content):
            part = cast(dict[str, Any], raw_part) if isinstance(raw_part, dict) else None
            if part is not None and part.get("type") == "text":
                text = part.get("text", "")
                if isinstance(text, str) and text:
                    parts.append(text)
            else:
                parts.append(json.dumps(raw_part, ensure_ascii=False))
    elif content is not None:
        parts.append(json.dumps(content, ensure_ascii=False))

    for key in ("name", "tool_call_id"):
        value = message.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    if message.get("tool_calls"):
        parts.append(json.dumps(message["tool_calls"], ensure_ascii=False))

    rc = (
        message.get("reasoning_content")
        or extract_reasoning(None, message.get("thinking_blocks"), None)[0]
    )
    if isinstance(rc, str) and rc:
        parts.append(rc)

    payload = "\n".join(parts)
    if not payload:
        return 4
    try:
        enc = token_encoding.get_token_encoding()
        if enc is not None:
            return max(4, len(enc.encode_ordinary(payload)) + 4)
    except Exception:
        pass
    return max(4, len(payload.encode("utf-8")) + 4)


def estimate_prompt_tokens_chain(
    provider: object,
    model: str | None,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[int, str]:
    """Estimate prompt tokens via provider, tiktoken, then a byte heuristic."""
    from cirno_core.providers.reasoning_history import prepare_reasoning_history

    messages = prepare_reasoning_history(provider, messages, tools=tools, for_count=True)
    provider_counter = getattr(provider, "estimate_prompt_tokens", None)
    if callable(provider_counter):
        with suppress(Exception):
            tokens, source = cast(tuple[object, object], provider_counter(messages, tools, model))
            if isinstance(tokens, (int, float)) and tokens > 0:
                return int(tokens), str(source or "provider_counter")
    estimated, source = _estimate_prompt_tokens_with_source(messages, tools)
    if estimated > 0:
        return int(estimated), source
    return 0, "none"
