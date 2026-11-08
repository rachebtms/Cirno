"""Tool identities, structured extras, and text-format tool calls."""

import json
import re
import secrets
import string
from typing import Any, cast

from cirno_core.providers.tool_calls import ToolCallRequest, parse_tool_arguments

from .wire import field

_ALNUM = string.ascii_letters + string.digits
_STANDARD_TC_KEYS = frozenset({"id", "type", "index", "function"})
_STANDARD_FN_KEYS = frozenset({"name", "arguments"})
_TEXT_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def short_tool_id() -> str:
    """9-char alphanumeric ID compatible with all providers (incl. Mistral)."""
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def extract_text_tool_calls(content: str | None) -> tuple[str | None, list[ToolCallRequest]]:
    """Normalize common text-format tool call blocks into structured calls."""
    if not content or "<tool_call>" not in content:
        return content, []

    tool_calls: list[ToolCallRequest] = []
    spans: list[tuple[int, int]] = []
    for match in _TEXT_TOOL_CALL_RE.finditer(content):
        try:
            raw_payload: object = json.loads(_strip_json_fence(match.group(1)))
        except (json.JSONDecodeError, RecursionError):
            continue
        if not isinstance(raw_payload, dict):
            continue
        payload = cast(dict[str, Any], raw_payload)

        nested = cast(object, payload.get("tool_call"))
        if isinstance(nested, dict):
            payload = cast(dict[str, Any], nested)
        function = cast(object, payload.get("function"))
        if not isinstance(function, dict):
            function = payload
        function_data = cast(dict[str, Any], function)
        name = cast(object, function_data.get("name"))
        if not isinstance(name, str) or not name:
            continue

        arguments = function_data.get(
            "arguments",
            payload.get("arguments", {}),
        )
        tool_calls.append(
            ToolCallRequest(
                id=str(payload.get("id") or short_tool_id()),
                name=name,
                arguments=parse_tool_arguments(arguments),
            )
        )
        spans.append(match.span())

    if not tool_calls:
        return content, []

    visible_parts: list[str] = []
    last = 0
    for start, end in spans:
        visible_parts.append(content[last:start])
        last = end
    visible_parts.append(content[last:])
    visible_content = "".join(visible_parts).strip() or None
    return visible_content, tool_calls


def _coerce_dict(value: object) -> dict[str, Any] | None:
    """Try to coerce *value* to a dict; return None if not possible or empty."""
    if value is None:
        return None
    if isinstance(value, dict):
        return cast(dict[str, Any], value) if value else None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped: object = model_dump()
        if isinstance(dumped, dict) and dumped:
            return cast(dict[str, Any], dumped)
    return None


def extract_tool_extras(
    tc: Any,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """Extract (extra_content, provider_specific_fields, fn_provider_specific_fields).

    Works for both SDK objects and dicts.  Captures Gemini ``extra_content``
    verbatim and any non-standard keys on the tool-call / function.
    """
    extra_content = _coerce_dict(field(tc, "extra_content"))

    tc_dict = _coerce_dict(tc)
    prov = None
    fn_prov = None
    if tc_dict is not None:
        leftover = {
            k: v
            for k, v in tc_dict.items()
            if k not in _STANDARD_TC_KEYS and k != "extra_content" and v is not None
        }
        if leftover:
            prov = leftover
        fn = _coerce_dict(tc_dict.get("function"))
        if fn is not None:
            fn_leftover = {
                k: v for k, v in fn.items() if k not in _STANDARD_FN_KEYS and v is not None
            }
            if fn_leftover:
                fn_prov = fn_leftover
    else:
        prov = _coerce_dict(field(tc, "provider_specific_fields"))
        fn_obj = field(tc, "function")
        if fn_obj is not None:
            fn_prov = _coerce_dict(field(fn_obj, "provider_specific_fields"))

    return extra_content, prov, fn_prov
