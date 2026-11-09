"""System events must not replace the Router's profile and reply contract."""
import json

import pytest

from cirno_core.providers.anthropic_provider import AnthropicProvider
from cirno_core.providers.openai_responses.converters import convert_messages


@pytest.mark.parametrize("blocks", [False, True])
def test_base_prompt_and_system_events_survive_native_conversion(blocks):
    base = "Router profile; replies require user__message"
    prefix = [{"type": "text", "text": base, "cache_control": {"type": "ephemeral"}}] if blocks else base
    messages = [{"role": "system", "content": prefix}, {"role": "user", "content": "hello"},
                {"role": "system", "content": "Awakening: introduce yourself"},
                {"role": "system", "content": [{"type": "text", "text": "Worker report: completed"}]}]
    response_system, response_messages = convert_messages(messages)
    anthropic = object.__new__(AnthropicProvider)
    anthropic_system, anthropic_messages = anthropic._convert_messages(messages)
    for system in (response_system, json.dumps(anthropic_system)):
        assert base in system
        assert "Awakening: introduce yourself" in system
        assert "Worker report: completed" in system
    assert response_messages[0]["role"] == "user"
    assert anthropic_messages[0]["role"] == "user"
    if blocks:
        assert anthropic_system[0]["cache_control"] == {"type": "ephemeral"}
    assert messages[0]["content"] == prefix
