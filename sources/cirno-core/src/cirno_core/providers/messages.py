"""Protocol message normalization shared by model transports."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.utils.text import sanitize_surrogates_deep

_SYNTHETIC_USER_CONTENT = "(conversation continued)"


def sanitize_empty_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitize message content: fix empty blocks, strip internal _meta fields.

    Also strips unpaired UTF-16 surrogate code points from every string leaf
    as a defense-in-depth pass before the payload leaves the process. Lone
    surrogates (e.g. leaking from a Windows console, prompt_toolkit history,
    or a truncated JSON round-trip) otherwise cause ``UnicodeEncodeError:
    'utf-8' codec can't encode characters ... surrogates not allowed`` when
    the HTTP client serializes the request body.
    """
    result: list[dict[str, Any]] = []
    for raw_msg in messages:
        msg = {key: value for key, value in raw_msg.items() if key != "_meta"}
        content = msg.get("content")

        if isinstance(content, str) and not content:
            clean = dict(msg)
            clean["content"] = (
                None if (msg.get("role") == "assistant" and msg.get("tool_calls")) else "(empty)"
            )
            result.append(clean)
            continue

        if isinstance(content, list):
            new_items: list[Any] = []
            changed = False
            for raw_item in cast(list[object], content):
                item = cast(dict[str, Any], raw_item) if isinstance(raw_item, dict) else None
                if (
                    item is not None
                    and item.get("type") in ("text", "input_text", "output_text")
                    and not item.get("text")
                ):
                    changed = True
                    continue
                if item is not None and "_meta" in item:
                    new_items.append({k: v for k, v in item.items() if k != "_meta"})
                    changed = True
                else:
                    new_items.append(raw_item)
            if changed:
                clean = dict(msg)
                if new_items:
                    clean["content"] = new_items
                elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                    clean["content"] = None
                else:
                    clean["content"] = "(empty)"
                result.append(clean)
                continue

        if isinstance(content, dict):
            clean = dict(msg)
            clean["content"] = [content]
            result.append(clean)
            continue

        result.append(msg)
    # Defense-in-depth: scrub lone UTF-16 surrogates from every string leaf.
    # This is idempotent and no-op when messages are already clean.
    sanitized = sanitize_surrogates_deep(result)
    return cast(list[dict[str, Any]], sanitized) if isinstance(sanitized, list) else result


def tool_name(tool: dict[str, Any]) -> str:
    """Extract tool name from either OpenAI or Anthropic-style tool schemas."""
    name = tool.get("name")
    if isinstance(name, str):
        return name
    fn = tool.get("function")
    fn_object = cast(dict[str, Any], fn) if isinstance(fn, dict) else None
    if fn_object is not None:
        fname = fn_object.get("name")
        if isinstance(fname, str):
            return fname
    return ""


def tool_cache_marker_indices(tools: list[dict[str, Any]]) -> list[int]:
    """Return cache marker indices: builtin/MCP boundary and tail index."""
    if not tools:
        return []

    tail_idx = len(tools) - 1
    last_builtin_idx: int | None = None
    for i in range(tail_idx, -1, -1):
        if not tool_name(tools[i]).startswith("mcp_"):
            last_builtin_idx = i
            break

    ordered_unique: list[int] = []
    for idx in (last_builtin_idx, tail_idx):
        if idx is not None and idx not in ordered_unique:
            ordered_unique.append(idx)
    return ordered_unique


def sanitize_request_messages(
    messages: list[dict[str, Any]],
    allowed_keys: frozenset[str],
) -> list[dict[str, Any]]:
    """Keep only provider-safe message keys and normalize assistant content."""
    sanitized: list[dict[str, Any]] = []
    for msg in messages:
        clean = {k: v for k, v in msg.items() if k in allowed_keys}
        if clean.get("role") == "assistant" and "content" not in clean:
            clean["content"] = None
        sanitized.append(clean)
    return sanitized


def content_as_blocks(content: Any) -> list[dict[str, Any]]:
    """Convert message content to blocks so mixed user content can be merged."""
    if isinstance(content, list):
        return [
            dict(cast(dict[str, Any], item))
            if isinstance(item, dict)
            else {"type": "text", "text": str(item)}
            for item in cast(list[object], content)
        ]
    if content is None:
        return []
    return [{"type": "text", "text": str(content)}]


def enforce_role_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive same-role messages and drop trailing assistant messages.

    Some providers (OpenAI-compat, Azure, vLLM, Ollama, etc.) reject requests
    where the last message is 'assistant' (prefill not supported) or two
    consecutive non-system messages share the same role.
    """
    if not messages:
        return messages

    merged: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if (
            merged
            and role != "system"
            and role not in ("tool",)
            and merged[-1].get("role") == role
            and role in ("user", "assistant")
        ):
            prev = merged[-1]
            if role == "assistant":
                prev_has_tools = bool(prev.get("tool_calls"))
                curr_has_tools = bool(msg.get("tool_calls"))
                if curr_has_tools:
                    merged[-1] = dict(msg)
                    continue
                if prev_has_tools:
                    continue
            prev_content = prev.get("content") or ""
            curr_content = msg.get("content") or ""
            if isinstance(prev_content, str) and isinstance(curr_content, str):
                prev["content"] = (prev_content + "\n\n" + curr_content).strip()
            elif role == "user":
                combined = dict(msg)
                combined["content"] = [
                    *content_as_blocks(prev_content),
                    *content_as_blocks(curr_content),
                ]
                merged[-1] = combined
            else:
                merged[-1] = dict(msg)
        else:
            merged.append(dict(msg))

    last_popped = None
    while merged and merged[-1].get("role") == "assistant":
        last_popped = merged.pop()

    # If removing trailing assistant messages left only system messages,
    # the request would be invalid for most providers (e.g. Zhipu/GLM
    # error 1214).  Recover by converting the last popped assistant
    # message to a user message so the LLM can still see the content.
    if (
        merged
        and last_popped is not None
        and not any(m.get("role") in ("user", "tool") for m in merged)
    ):
        recovered = dict(last_popped)
        recovered["role"] = "user"
        merged.append(recovered)

    # Safety net: ensure the first non-system message is not a bare
    # ``assistant`` message.  Providers like GLM reject system→assistant
    # with error 1214.  Insert a synthetic user message to keep the
    # sequence valid when replayed history starts at an assistant turn.
    for i, msg in enumerate(merged):
        if msg.get("role") != "system":
            if msg.get("role") == "assistant" and not msg.get("tool_calls"):
                merged.insert(i, {"role": "user", "content": _SYNTHETIC_USER_CONTENT})
            break

    return merged


def strip_image_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Replace image_url blocks with text placeholder. Returns None if no images found."""
    found = False
    result: list[dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            new_content: list[Any] = []
            for raw_block in cast(list[object], content):
                block = cast(dict[str, Any], raw_block) if isinstance(raw_block, dict) else None
                if block is not None and block.get("type") == "image_url":
                    placeholder = "[Image not delivered to model — do not describe or reference it]"
                    new_content.append({"type": "text", "text": placeholder})
                    found = True
                else:
                    new_content.append(raw_block)
            result.append({**msg, "content": new_content})
        else:
            result.append(msg)
    return result if found else None


def contains_image_content(value: object) -> bool:
    """Return whether a JSON-like provider payload contains an input image."""
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        if mapping.get("type") in {"image_url", "input_image"}:
            return True
        return any(contains_image_content(item) for item in mapping.values())
    if isinstance(value, list):
        return any(contains_image_content(item) for item in cast(list[object], value))
    return False


def strip_image_content_inplace(messages: list[dict[str, Any]]) -> bool:
    """Replace image_url blocks with text placeholder *in-place*.

    Mutates the content lists of the original message dicts so that
    callers holding references to those dicts also see the stripped
    version.
    """
    found = False
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for i, raw_block in enumerate(cast(list[object], content)):
                block = cast(dict[str, Any], raw_block) if isinstance(raw_block, dict) else None
                if block is not None and block.get("type") == "image_url":
                    placeholder = "[Image not delivered to model — do not describe or reference it]"
                    content[i] = {"type": "text", "text": placeholder}
                    found = True
    return found
