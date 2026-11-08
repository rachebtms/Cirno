"""Merge provider wire-body overrides while retaining generated tools."""

import json
from typing import Any, cast


def merge_objects(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*, returning a new dict.

    Nested dicts are merged key-by-key; all other types in *override*
    replace the corresponding key in *base*.
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_objects(
                cast(dict[str, Any], merged[key]),
                cast(dict[str, Any], value),
            )
        else:
            merged[key] = value
    return merged


def merge_unique_list(base: object, override: object) -> object:
    """Append list values while preserving order and removing duplicates."""
    if not isinstance(base, list) or not isinstance(override, list):
        return override
    result: list[object] = []
    seen: set[str] = set()
    for value in [
        *cast(list[object], base),
        *cast(list[object], override),
    ]:
        try:
            key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        except Exception:
            key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def merge_chat_extra_body(
    kwargs: dict[str, Any],
    extra_body: dict[str, Any],
) -> dict[str, Any]:
    """Merge configured Chat Completions fields without clobbering tools."""
    regular_extra = {key: value for key, value in extra_body.items() if key != "tools"}
    merged = dict(kwargs)
    if regular_extra:
        existing = kwargs.get("extra_body", {})
        merged["extra_body"] = merge_objects(existing, regular_extra)

    if "tools" in extra_body:
        current_tools = kwargs.get("tools")
        configured_tools = extra_body["tools"]
        if isinstance(current_tools, list) and isinstance(configured_tools, list):
            merged["tools"] = [*current_tools, *configured_tools]
        else:
            merged["tools"] = configured_tools

    return merged


def merge_responses_extra_body(
    body: dict[str, Any],
    extra_body: dict[str, Any],
) -> dict[str, Any]:
    """Merge configured Responses API body fields without clobbering tools."""
    reserved = {"include", "tools"}
    regular_extra = {key: value for key, value in extra_body.items() if key not in reserved}
    merged = merge_objects(body, regular_extra)

    if "include" in extra_body:
        merged["include"] = merge_unique_list(body.get("include"), extra_body["include"])

    if "tools" in extra_body:
        current_tools = body.get("tools")
        configured_tools = extra_body["tools"]
        if isinstance(current_tools, list) and isinstance(configured_tools, list):
            merged["tools"] = [*current_tools, *configured_tools]
        else:
            merged["tools"] = configured_tools

    return merged
