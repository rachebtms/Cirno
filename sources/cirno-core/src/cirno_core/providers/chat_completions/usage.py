"""Normalize provider usage and explicit zero-valued cache counters."""

from typing import Any, cast

from cirno_usage.types import LLMUsage

from .wire import mapping


def extract_usage(response: Any) -> LLMUsage | None:
    """Extract token usage from an OpenAI-compatible response.

    Handles both dict-based (raw JSON) and object-based (SDK Pydantic)
    responses. Provider-specific cache fields are normalized once at
    this Chat Completions wire boundary.
    """
    # --- resolve usage object ---
    usage_obj = None
    response_map = mapping(response)
    if response_map is not None:
        usage_obj = response_map.get("usage")
    elif hasattr(response, "usage") and response.usage:
        usage_obj = response.usage

    usage_map = mapping(usage_obj)
    if usage_map is not None:
        input_tokens = int(usage_map.get("prompt_tokens") or 0)
        output_tokens = int(usage_map.get("completion_tokens") or 0)
    elif usage_obj:
        input_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
    else:
        return None

    wire_total = nested_int(usage_obj, ("total_tokens",))

    cache_read: int | None = None
    # --- cached_tokens (normalised across Chat-compatible providers) ---
    # Try nested paths first (dict), fall back to attribute (SDK object).
    # Priority order ensures the most specific field wins.
    for path in (
        ("prompt_tokens_details", "cached_tokens"),  # OpenAI/Zhipu/MiniMax/Qwen/Mistral/xAI
        ("cached_tokens",),  # StepFun/Moonshot (top-level)
        ("prompt_cache_hit_tokens",),  # DeepSeek/SiliconFlow
    ):
        cached = nested_int(usage_map, path)
        if cached is None and usage_obj:
            cached = nested_int(usage_obj, path)
        if cached is not None:
            cache_read = cached
            break

    cache_write = nested_int(
        usage_obj,
        ("prompt_tokens_details", "cache_write_tokens"),
    )

    return LLMUsage.reported(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=wire_total,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )


def nested_int(obj: object, path: tuple[str, ...]) -> int | None:
    """Return a present usage count while preserving explicit zero.

    Supports both dict-key access and attribute access so it works
    uniformly with raw JSON dicts **and** SDK Pydantic models.
    """
    current: object = obj
    for segment in path:
        if current is None:
            return None
        if isinstance(current, dict):
            current = cast(dict[str, Any], current).get(segment)
        else:
            current = getattr(current, segment, None)
    if current is None or isinstance(current, bool):
        return None
    try:
        return int(cast(Any, current))
    except (TypeError, ValueError):
        return None
