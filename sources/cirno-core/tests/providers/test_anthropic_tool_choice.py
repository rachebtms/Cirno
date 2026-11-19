"""An explicit no-tools request retains stable context and tool schemas."""

from copy import deepcopy

import pytest
from cirno_core.providers.anthropic_provider import AnthropicProvider


@pytest.mark.parametrize("reasoning", [None, "low"])
@pytest.mark.parametrize("caching", [False, True])
def test_explicit_none_disables_tools_without_rewriting_the_cached_prefix(reasoning, caching):
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.default_model = "claude-sonnet-4-6"
    provider._spec = None
    provider.extra_headers = {}
    provider._extra_body = {}
    messages = [{"role": "system", "content": "Stable system prefix"}, {"role": "user", "content": "Only answer"}]
    tools = [{"type": "function", "function": {"name": "files_read", "parameters": {"type": "object"}}}]
    before = deepcopy((messages, tools))
    auto = provider._build_kwargs(messages, tools, None, 4096, 0.7, reasoning, "auto", supports_caching=caching)
    none = provider._build_kwargs(messages, tools, None, 4096, 0.7, reasoning, "none", supports_caching=caching)
    assert none["tool_choice"] == {"type": "none"}
    assert {key: value for key, value in none.items() if key != "tool_choice"} == {
        key: value for key, value in auto.items() if key != "tool_choice"
    }
    assert (messages, tools) == before


@pytest.mark.parametrize("choice,thinking,expected", [
    ("auto", False, {"type": "auto"}),
    ("required", False, {"type": "any"}),
    ({"type": "function", "function": {"name": "files_read"}}, False, {"type": "tool", "name": "files_read"}),
    ("required", True, {"type": "auto"}),
])
def test_other_native_tool_choice_policies_keep_existing_behavior(choice, thinking, expected):
    assert AnthropicProvider._convert_tool_choice(choice, thinking) == expected
