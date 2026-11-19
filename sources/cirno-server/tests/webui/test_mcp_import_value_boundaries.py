"""MCP import/form value types are checked before configuration can be persisted."""

import json

import pytest
from cirno_server.webui.mcp.contracts import McpPresetError
from cirno_server.webui.mcp.parsing import custom_server_from_query, import_mcp_servers


@pytest.mark.parametrize(('field', 'value'), [
    ('args', False), ('args', 0), ('args', ''), ('args', {}),
    ('env', False), ('env', 0), ('env', ''), ('env', []),
    ('headers', False), ('headers', 0), ('headers', ''), ('headers', []),
])
def test_import_does_not_turn_falsey_malformed_containers_into_empty_values(field, value):
    server = {'command': 'fixture-mcp', field: value}
    with pytest.raises(McpPresetError):
        import_mcp_servers(json.dumps({'mcpServers': {'fixture': server}}))


@pytest.mark.parametrize(('field', 'value'), [('command', 7), ('command', ['fixture-mcp']), ('url', 7), ('cwd', ['cwd']),
    ('type', False), ('cwd', 7), ('url', []), ('auth', False)])
def test_import_does_not_coerce_connection_objects_into_strings(field, value):
    server = {'command': 'fixture-mcp', field: value}
    with pytest.raises(McpPresetError):
        import_mcp_servers(json.dumps({'mcpServers': {'fixture': server}}))


def test_shell_style_argument_quote_errors_are_reported_as_form_validation_errors():
    with pytest.raises(McpPresetError):
        custom_server_from_query({'name': ['fixture'], 'command': ['fixture-mcp'], 'args': [json.dumps('--flag "unterminated')]})


def test_import_rejects_trailing_newline_in_a_server_identity():
    with pytest.raises(McpPresetError):
        import_mcp_servers(json.dumps({'mcpServers': {'fixture\n': {'command': 'fixture-mcp'}}}))


def test_import_does_not_silently_overwrite_colliding_normalized_identities():
    with pytest.raises(McpPresetError):
        import_mcp_servers(json.dumps({'mcpServers': {
            'Fixture': {'command': 'first-command'}, 'fixture': {'command': 'second-command'},
        }}))


@pytest.mark.parametrize('containers', [None, 'empty'])
def test_import_keeps_optional_null_and_correct_empty_containers_compatible(containers):
    server = {'command': 'fixture-mcp', 'args': None, 'env': None, 'headers': None}
    if containers == 'empty':
        server.update(args=[], env={}, headers={})
    config = import_mcp_servers(json.dumps({'mcpServers': {'Fixture': server}}))['fixture']
    assert config.args == [] and config.env == {} and config.headers == {}
    assert 'enabled_tools' not in config.model_fields_set


def test_form_preserves_quoted_literal_arguments_in_a_json_array():
    args = ['--label', 'A "quoted" value', 'two words']
    _, config = custom_server_from_query({'name': ['fixture'], 'command': ['fixture-mcp'], 'args': [json.dumps(args)]})
    assert config.args == args


def test_invalid_bulk_import_leaves_existing_servers_and_storage_untouched(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from cirno_core.config.tools import MCPServerConfig
    from cirno_server.webui.mcp import configuration
    existing = {'saved': MCPServerConfig(command='saved-command', enabled_tools=['read'])}
    config = SimpleNamespace(tools=SimpleNamespace(mcp_servers=existing.copy()))
    saved = Mock()
    monkeypatch.setattr(configuration, 'load_config', lambda *args, **kwargs: config)
    monkeypatch.setattr(configuration, 'save_config', saved)
    payload = {'mcpServers': {'new-valid': {'command': 'valid-command'}, 'invalid': {'command': 'other-command', 'args': False}}}
    with pytest.raises(McpPresetError) as error:
        configuration.custom_mcp_action('import', {'config': [json.dumps(payload)]})
    assert error.value.status == 400
    assert config.tools.mcp_servers == existing
    saved.assert_not_called()
