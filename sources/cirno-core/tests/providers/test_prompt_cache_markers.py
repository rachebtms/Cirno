from __future__ import annotations

from cirno_core.providers.chat_completions.cache import apply_cache_control
from typing import Any

from cirno_core.providers.anthropic_provider import AnthropicProvider


def _openai_tools(*names: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


def _anthropic_tools(*names: str) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": f"{name} tool",
            "input_schema": {"type": "object", "properties": {}},
        }
        for name in names
    ]


def _marked_openai_tool_names(tools: list[dict[str, Any]] | None) -> list[str]:
    if not tools:
        return []
    marked: list[str] = []
    for tool in tools:
        if "cache_control" in tool:
            marked.append((tool.get("function") or {}).get("name", ""))
    return marked


def _marked_anthropic_tool_names(tools: list[dict[str, Any]] | None) -> list[str]:
    if not tools:
        return []
    return [tool.get("name", "") for tool in tools if "cache_control" in tool]


def test_openai_compat_marks_builtin_boundary_and_tail_tool() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "assistant"},
        {"role": "user", "content": "user"},
    ]
    _, marked_tools = apply_cache_control(
        messages,
        _openai_tools("read_file", "write_file", "mcp_fs_ls", "mcp_git_status"),
    )
    assert _marked_openai_tool_names(marked_tools) == ["write_file", "mcp_git_status"]


def test_anthropic_marks_builtin_boundary_and_tail_tool() -> None:
    messages = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
    ]
    _, _, marked_tools = AnthropicProvider._apply_cache_control(
        "system",
        messages,
        _anthropic_tools("read_file", "write_file", "mcp_fs_ls", "mcp_git_status"),
    )
    assert _marked_anthropic_tool_names(marked_tools) == ["write_file", "mcp_git_status"]


def test_openai_compat_marks_only_tail_without_mcp() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": "assistant"},
        {"role": "user", "content": "user"},
    ]
    _, marked_tools = apply_cache_control(
        messages,
        _openai_tools("read_file", "write_file"),
    )
    assert _marked_openai_tool_names(marked_tools) == ["write_file"]


def test_cache_markers_include_first_user_input_and_do_not_mutate_it() -> None:
    from copy import deepcopy

    messages = [{"role": "system", "content": "stable rules"}, {"role": "user", "content": "long document"}]
    original = deepcopy(messages)
    marked, _ = apply_cache_control(messages, None)
    assert "cache_control" in marked[-1]["content"][-1]
    _, native, _ = AnthropicProvider._apply_cache_control("stable rules", messages[1:], None)
    assert "cache_control" in native[-1]["content"][-1]
    assert messages == original


def test_cache_markers_include_latest_tool_result() -> None:
    messages = [
        {"role": "user", "content": "inspect"},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "tool_call_id": "read-1", "content": "large tool result"},
    ]
    marked, _ = apply_cache_control(messages, None)
    assert marked[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert marked[1] == messages[1]
    native_messages = [
        {"role": "user", "content": "inspect"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "read-1", "name": "read", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "read-1", "content": "large tool result"}]},
    ]
    _, marked_native, _ = AnthropicProvider._apply_cache_control("rules", native_messages, None)
    assert "cache_control" in marked_native[-1]["content"][-1]
    assert "cache_control" not in native_messages[-1]["content"][-1]


def test_anthropic_cache_marker_does_not_target_thinking_or_empty_text() -> None:
    messages = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "private", "signature": "sig"}, {"type": "text", "text": ""}]},
    ]
    _, marked, _ = AnthropicProvider._apply_cache_control("rules", messages, None)
    assert marked[0]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert marked[1] == messages[1]
