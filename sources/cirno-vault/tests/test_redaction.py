"""Malformed credential calls stay private without changing execution arguments."""

import json

import pytest
from cirno_vault.redaction import tool_arguments


@pytest.mark.parametrize("name", ["credential", "credentials.store", "credentials__store"])
@pytest.mark.parametrize("arguments", [
    '{"value": "private-secret"',
    {"username": "private-secret", "action": "store"},
    ["private-secret"],
    '"private-secret"',
])
def test_sensitive_arguments_never_leak_when_the_call_is_invalid(name, arguments):
    result = tool_arguments(name, arguments)
    assert "private-secret" not in json.dumps(result)
    assert "private-secret" in json.dumps(arguments)


def test_ordinary_tool_arguments_are_unchanged():
    arguments = '{not-json'
    assert tool_arguments("files.read", arguments) is arguments


@pytest.mark.parametrize("name", ["credentials__read", "credentials.read", "credential"])
@pytest.mark.parametrize("protocol", ["chat", "responses"])
def test_read_results_redact_by_call_id_without_mutating_live_context(name, protocol):
    from copy import deepcopy
    from cirno_vault.redaction import CREDENTIAL_RESULT_HIDDEN, tool_history

    function = {"name": name, "arguments": '{"action":"read","id":"saved-id"}'}
    if protocol == "chat":
        messages = [
            {"role": "assistant", "tool_calls": [{"id": "read", "function": function}]},
            {"role": "tool", "tool_call_id": "read", "content": "private-secret"},
        ]
        key = "content"
    else:
        messages = [
            {"type": "function_call", "call_id": "read", **function},
            {"type": "function_call_output", "call_id": "read", "output": "private-secret"},
        ]
        key = "output"
    before = deepcopy(messages)
    durable = tool_history(messages)
    assert durable[-1][key] == CREDENTIAL_RESULT_HIDDEN
    assert durable[-1].get("tool_call_id", durable[-1].get("call_id")) == "read"
    assert durable[0] is messages[0]
    assert messages == before
    assert tool_history(durable) is durable


def test_nonsecret_results_preserve_prefix_identity():
    from cirno_vault.redaction import tool_history

    messages = [{"role": "tool", "name": "files__read", "content": "ordinary content"}]
    assert tool_history(messages) is messages


def test_native_credential_store_arguments_are_not_saved_in_plaintext():
    from cirno_vault.redaction import tool_history

    messages = [{"type": "function_call", "call_id": "store", "name": "credentials__store",
                 "arguments": '{"label":"Saved","value":"private-secret"}'}]
    durable = tool_history(messages)
    assert "private-secret" not in json.dumps(durable)
    assert json.loads(durable[0]["arguments"])["label"] == "Saved"
    assert "private-secret" in messages[0]["arguments"]
