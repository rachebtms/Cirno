"""Normalize provider-specific history without changing the captured transcript."""

import hashlib
import json
from collections import deque
from typing import Any, cast

from cirno_core.providers.messages import enforce_role_alternation, sanitize_request_messages
from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.tool_calls import tool_arguments_json_for_replay

from .text import extract_text
from .tools import short_tool_id

_GEMINI_SKIP_THOUGHT_SIGNATURE = "skip_thought_signature_validator"
_ALLOWED_MSG_KEYS = frozenset(
    {"role", "content", "tool_calls", "tool_call_id", "name", "reasoning_content", "extra_content"}
)


def normalize_tool_call_id(tool_call_id: Any) -> Any:
    """Normalize to a provider-safe 9-char alphanumeric form."""
    if not isinstance(tool_call_id, str):
        return tool_call_id
    if len(tool_call_id) == 9 and tool_call_id.isalnum():
        return tool_call_id
    return hashlib.sha1(tool_call_id.encode()).hexdigest()[:9]


def coerce_content_to_string(content: Any) -> str | None:
    """Coerce block/list content into plain text for strict string-only APIs."""
    if content is None or isinstance(content, str):
        return content
    text = extract_text(content)
    if isinstance(text, str) and text:
        return text
    try:
        dumped = json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError):
        dumped = str(content)
    return dumped or "(empty)"


def gemini_thought_signature(tool_call: dict[str, Any]) -> str | None:
    """Return Gemini's thought signature attached to a tool call, if any.

    Gemini's OpenAI-compatible endpoint returns tool calls with an
    ``extra_content`` field: ``{"google": {"thought_signature": "..."}}``.
    cirno preserves it through the parse -> serialize round-trip so
    replayed calls stay valid. Calls produced by other providers (e.g.
    after a mid-conversation model switch) carry no signature.
    """
    extra = tool_call.get("extra_content")
    if not isinstance(extra, dict):
        return None
    google = cast(dict[str, Any], extra).get("google")
    if not isinstance(google, dict):
        return None
    signature = cast(dict[str, Any], google).get("thought_signature")
    if isinstance(signature, str) and signature:
        return signature
    return None


def ensure_gemini_thought_signatures(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep migrated tool history wire-valid without losing tool context.

    Gemini requires the first call in each function-call step to carry a
    thought signature. Native parallel calls intentionally leave later
    calls unsigned, so they must remain in their original order. For a
    fully unsigned step imported from another provider, Google documents
    ``skip_thought_signature_validator`` as a last-resort migration value.
    """
    kept: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        calls = msg.get("tool_calls")
        if role != "assistant" or not isinstance(calls, list) or not calls:
            kept.append(msg)
            continue

        call_values = cast(list[object], calls)
        typed_calls = [
            cast(dict[str, Any], tool_call)
            for tool_call in call_values
            if isinstance(tool_call, dict)
        ]
        if not typed_calls:
            if msg.get("content"):
                clean = dict(msg)
                clean.pop("tool_calls", None)
                kept.append(clean)
            continue

        clean_calls = typed_calls
        if gemini_thought_signature(typed_calls[0]) is None:
            first = dict(typed_calls[0])
            extra_value = first.get("extra_content")
            extra = dict(cast(dict[str, Any], extra_value)) if isinstance(extra_value, dict) else {}
            google_value = extra.get("google")
            google = (
                dict(cast(dict[str, Any], google_value)) if isinstance(google_value, dict) else {}
            )
            google["thought_signature"] = _GEMINI_SKIP_THOUGHT_SIGNATURE
            extra["google"] = google
            first["extra_content"] = extra
            clean_calls = [first, *typed_calls[1:]]

        if clean_calls != call_values:
            msg = dict(msg)
            msg["tool_calls"] = clean_calls
        kept.append(msg)
    return kept


def sanitize_messages(
    messages: list[dict[str, Any]],
    *,
    spec: ProviderSpec | None,
    model: str,
) -> list[dict[str, Any]]:
    """Strip non-standard keys, normalize tool_call IDs."""
    sanitized = sanitize_request_messages(messages, _ALLOWED_MSG_KEYS)
    id_map: dict[str, str] = {}
    pending_tool_ids: dict[str, deque[str]] = {}
    force_string_content = False
    if spec and spec.name == "deepseek":
        metadata = spec.model_metadata(model)
        force_string_content = metadata is None or "image" not in metadata.input_modalities
    normalize_tool_ids = bool(spec and spec.name == "mistral")
    if spec and spec.name == "gemini":
        sanitized = ensure_gemini_thought_signatures(sanitized)

    def map_id(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if not normalize_tool_ids:
            return value
        return id_map.setdefault(value, normalize_tool_call_id(value))

    def unique_tool_id(value: Any, used_ids: set[str], idx: int) -> str:
        if isinstance(value, str) and value:
            base = map_id(value)
        else:
            base = short_tool_id()
        if not isinstance(base, str) or not base:
            base = short_tool_id()
        if base not in used_ids:
            return base
        seed = value if isinstance(value, str) and value else base
        salt = 1
        while True:
            candidate = normalize_tool_call_id(f"{seed}:{idx}:{salt}")
            if isinstance(candidate, str) and candidate not in used_ids:
                return candidate
            salt += 1

    def map_tool_result_id(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        queue = pending_tool_ids.get(value)
        if queue:
            mapped = queue.popleft()
            if not queue:
                pending_tool_ids.pop(value, None)
            return mapped
        return map_id(value)

    for clean in sanitized:
        tool_calls_value = cast(object, clean.get("tool_calls"))
        if isinstance(tool_calls_value, list):
            normalized: list[Any] = []
            used_ids: set[str] = set()
            for idx, tc in enumerate(cast(list[object], tool_calls_value)):
                if not isinstance(tc, dict):
                    normalized.append(tc)
                    continue
                tc_clean = dict(cast(dict[str, Any], tc))
                raw_id = tc_clean.get("id")
                mapped_id = unique_tool_id(raw_id, used_ids, idx)
                tc_clean["id"] = mapped_id
                used_ids.add(mapped_id)
                if isinstance(raw_id, str) and raw_id:
                    pending_tool_ids.setdefault(raw_id, deque()).append(mapped_id)
                function = cast(object, tc_clean.get("function"))
                if isinstance(function, dict):
                    function_clean = dict(cast(dict[str, Any], function))
                    if "arguments" in function_clean:
                        function_clean["arguments"] = tool_arguments_json_for_replay(
                            function_clean.get("arguments")
                        )
                    else:
                        function_clean["arguments"] = "{}"
                    tc_clean["function"] = function_clean
                normalized.append(tc_clean)
            clean["tool_calls"] = normalized
        if "tool_call_id" in clean and clean["tool_call_id"]:
            clean["tool_call_id"] = map_tool_result_id(clean["tool_call_id"])
        if force_string_content and not (
            clean.get("role") == "assistant" and clean.get("tool_calls")
        ):
            clean["content"] = coerce_content_to_string(clean.get("content"))
    return enforce_role_alternation(sanitized)
