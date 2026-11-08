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
