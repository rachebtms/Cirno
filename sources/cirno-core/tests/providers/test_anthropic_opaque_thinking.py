"""Native encrypted thinking survives parsing and cache-aware tool replay."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from anthropic.types.redacted_thinking_block import RedactedThinkingBlock
from cirno_core.providers.anthropic_provider import AnthropicProvider
from cirno_core.utils.model_messages import build_assistant_message


def provider():
    instance = AnthropicProvider.__new__(AnthropicProvider)
    instance.default_model = "claude-sonnet-4-6"
    instance._spec = None
    instance.extra_headers = {}
    instance._extra_body = {}
    return instance


def native_response():
    return SimpleNamespace(content=[
        RedactedThinkingBlock(type="redacted_thinking", data="opaque-encrypted-thinking"),
        SimpleNamespace(type="thinking", thinking="check the file", signature="opaque-signature"),
        SimpleNamespace(type="tool_use", id="call_native", name="files_read", input={"path": "notes.txt"}),
    ], stop_reason="tool_use", usage=None)


def test_native_response_retains_redacted_thinking_in_block_order():
    response = AnthropicProvider._parse_response(native_response())
    assert response.thinking_blocks == [
        {"type": "redacted_thinking", "data": "opaque-encrypted-thinking"},
        {"type": "thinking", "thinking": "check the file", "signature": "opaque-signature"},
    ]
    assert response.content is None
    assert response.tool_calls[0].arguments == {"path": "notes.txt"}


@pytest.mark.parametrize("caching", [False, True])
def test_opaque_thinking_is_replayed_unchanged_without_cache_marker(caching):
    thinking = [
        {"type": "redacted_thinking", "data": "opaque-encrypted-thinking"},
        {"type": "thinking", "thinking": "check the file", "signature": "opaque-signature"},
    ]
    assistant = build_assistant_message("", thinking_blocks=thinking, tool_calls=[{
        "id": "call_native", "type": "function", "function": {"name": "files_read", "arguments": '{"path":"notes.txt"}'},
    }])
    messages = [
        {"role": "system", "content": "Stable system prefix"},
        {"role": "user", "content": "Inspect notes"}, assistant,
        {"role": "tool", "tool_call_id": "call_native", "content": "The file content"},
    ]
    original = deepcopy(messages)
    kwargs = provider()._build_kwargs(messages, [{"type": "function", "function": {"name": "files_read", "parameters": {"type": "object"}}}], None, 4096, 0.7, "low", None, supports_caching=caching)
    assert kwargs["messages"][1]["content"][:2] == thinking
    assert all("cache_control" not in block for block in kwargs["messages"][1]["content"][:2])
    assert messages == original


def test_foreign_redacted_block_without_anthropic_data_is_not_sent_as_empty_ciphertext():
    blocks = provider()._assistant_blocks({"role": "assistant", "thinking_blocks": [{
        "type": "redacted_thinking", "redactedContentBase64": "foreign-format",
    }], "content": "Answer"})
    assert blocks == [{"type": "text", "text": "Answer"}]
