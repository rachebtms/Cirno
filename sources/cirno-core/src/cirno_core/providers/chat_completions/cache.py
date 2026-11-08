"""Mark stable prefix boundaries for compatible prompt caches."""

from typing import Any, cast

from cirno_core.providers.messages import tool_cache_marker_indices


def apply_cache_control(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Inject cache_control markers for prompt caching."""
    cache_marker = {"type": "ephemeral"}
    new_messages = list(messages)

    def _mark(msg: dict[str, Any]) -> dict[str, Any]:
        content = msg.get("content")
        if isinstance(content, str) and content:
            return {
                **msg,
                "content": [
                    {"type": "text", "text": content, "cache_control": cache_marker},
                ],
            }
        if isinstance(content, list) and content:
            nc = list(cast(list[dict[str, Any]], content))
            cacheable = next(
                (
                    index
                    for index in range(len(nc) - 1, -1, -1)
                    if nc[index].get("type") in {"text", "image_url"}
                    and (nc[index].get("type") != "text" or nc[index].get("text"))
                ),
                None,
            )
            if cacheable is not None:
                nc[cacheable] = {**nc[cacheable], "cache_control": cache_marker}
                return {**msg, "content": nc}
        return msg

    if new_messages and new_messages[0].get("role") == "system":
        new_messages[0] = _mark(new_messages[0])
    # Cache the complete input, including a first-turn document or the
    # latest tool result. Marking only the penultimate message leaves this
    # suffix uncached when the next tool round appends to it.
    for index in range(len(new_messages) - 1, -1, -1):
        if new_messages[index].get("role") == "system":
            continue
        marked = _mark(new_messages[index])
        if marked is not new_messages[index]:
            new_messages[index] = marked
            break

    new_tools = tools
    if tools:
        new_tools = list(tools)
        for idx in tool_cache_marker_indices(new_tools):
            new_tools[idx] = {**new_tools[idx], "cache_control": cache_marker}
    return new_messages, new_tools
