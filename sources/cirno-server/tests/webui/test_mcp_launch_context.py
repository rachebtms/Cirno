"""Dependency and proxy checks use the selected launch context without launching it."""

import json
import os

import pytest
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.contracts import McpPresetError
from cirno_server.webui.mcp.fields import config_available, validate_proxy
from cirno_server.webui.mcp.parsing import import_mcp_servers


@pytest.fixture
def executable(tmp_path, monkeypatch):
    directory = tmp_path / 'owned'
    directory.mkdir()
    name = 'fixture-mcp.exe' if os.name == 'nt' else 'fixture-mcp'
    path = directory / name
    path.write_text('fixture, never executed')
    path.chmod(0o700)
    absent = tmp_path / 'absent-path'
    absent.mkdir()
    monkeypatch.setenv('PATH', str(absent))
    return directory, path


@pytest.mark.parametrize('kind', ['custom-path', 'relative-command', 'empty-path', 'relative-path', 'environment-reference'])
def test_stdio_availability_follows_its_configured_cwd_and_path(executable, tmp_path, monkeypatch, kind):
    directory, path = executable
    if kind == 'custom-path':
        cfg = MCPServerConfig(command=path.name, env={'PATH': str(directory)})
    elif kind == 'relative-command':
        cfg = MCPServerConfig(command=f'./{path.name}', cwd=str(directory))
    elif kind == 'empty-path':
        cfg = MCPServerConfig(command=path.name, cwd=str(directory), env={'PATH': ''})
    elif kind == 'relative-path':
        cfg = MCPServerConfig(command=path.name, cwd=str(tmp_path), env={'PATH': 'owned'})
    else:
        monkeypatch.setenv('CIRNO_FIXTURE_BIN', str(directory))
        cfg = MCPServerConfig(command=path.name, env={'PATH': '${CIRNO_FIXTURE_BIN}'})
    assert config_available(cfg) is True


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable permission bits')
def test_an_existing_nonexecutable_file_is_not_a_launchable_stdio_command(executable):
    _, path = executable
    path.chmod(0o600)
    assert config_available(MCPServerConfig(command=str(path))) is False


def test_an_invalid_cwd_cannot_be_reported_as_a_configured_executable(executable, tmp_path):
    _, path = executable
    assert config_available(MCPServerConfig(command=str(path), cwd=str(tmp_path / 'missing'))) is False


@pytest.mark.parametrize('transport', ['sse', 'streamableHttp'])
def test_an_ignored_stdio_command_does_not_prevent_remote_proxy_configuration(transport):
    cfg = MCPServerConfig(type=transport, command='ignored-obsolete-command', url='https://fixture.test/mcp', use_proxy=True)
    validate_proxy(cfg, NetworkConfig(proxy='http://fixture-proxy.test:8080'))


@pytest.mark.parametrize('timeout', [True, False, 1.5, float('inf'), float('-inf'), float('nan'), 'not-a-number', [], {}])
def test_invalid_import_timeouts_are_rejected_instead_of_truncated_or_defaulted(timeout):
    with pytest.raises(McpPresetError):
        import_mcp_servers(json.dumps({'mcpServers': {'fixture': {'command': 'fixture-mcp', 'toolTimeout': timeout}}}))


@pytest.mark.parametrize('field', ['PATH', 'cwd'])
def test_unset_command_context_references_do_not_adopt_defaults(executable, monkeypatch, field):
    directory, path = executable
    monkeypatch.delenv('CIRNO_FIXTURE_UNSET', raising=False)
    cfg = MCPServerConfig(command=str(path), cwd=str(directory))
    if field == 'PATH':
        cfg.env['PATH'] = '${CIRNO_FIXTURE_UNSET}'
    else:
        cfg.cwd = '${CIRNO_FIXTURE_UNSET}'
    assert config_available(cfg) is False


@pytest.mark.parametrize('field', ['PATH', 'cwd'])
def test_explicitly_empty_command_context_references_remain_valid(executable, monkeypatch, field):
    directory, path = executable
    monkeypatch.setenv('CIRNO_FIXTURE_EMPTY', '')
    cfg = MCPServerConfig(command=str(path), cwd=str(directory))
    if field == 'PATH':
        cfg.env['PATH'] = '${CIRNO_FIXTURE_EMPTY}'
    else:
        cfg.cwd = '${CIRNO_FIXTURE_EMPTY}'
    assert config_available(cfg) is True


@pytest.mark.parametrize(('value', 'expected'), [(None, 30), ('', 30), ('45', 45), (45, 45), (0, 5), (900, 600)])
def test_custom_form_and_import_share_timeout_defaults_and_bounds(value, expected):
    from cirno_server.webui.mcp.parsing import custom_server_from_query
    cfg = import_mcp_servers(json.dumps({'mcpServers': {'fixture': {'command': 'fixture-mcp', 'toolTimeout': value}}}))['fixture']
    query = {'name': ['fixture'], 'command': ['fixture-mcp']}
    if value is not None:
        query['tool_timeout'] = [str(value)]
    _, form = custom_server_from_query(query)
    assert cfg.tool_timeout == form.tool_timeout == expected


@pytest.mark.parametrize('kind', ['relative-command', 'environment-reference'])
async def test_catalog_and_inspection_use_the_same_configured_executable(executable, tmp_path, monkeypatch, kind):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config
    from cirno_server.webui.mcp.catalog import mcp_presets_payload
    from cirno_server.webui.mcp.inspection import mcp_presets_test_action
    directory, path = executable
    if kind == 'relative-command':
        cfg = MCPServerConfig(command=f'./{path.name}', cwd=str(directory))
    else:
        monkeypatch.setenv('CIRNO_FIXTURE_BIN', str(directory))
        cfg = MCPServerConfig(command=path.name, env={'PATH': '${CIRNO_FIXTURE_BIN}'})
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / 'workspace')
    config.tools.mcp_servers['fixture'] = cfg
    config_path = tmp_path / 'config.json'
    save_config(config, config_path)
    calls = []
    closed = AsyncMock()
    async def connect(servers, registry, **kwargs):
        calls.append(servers['fixture'])
        return {'fixture': SimpleNamespace(aclose=closed)}
    monkeypatch.setattr('cirno_core.agent.tools.mcp.connector.connect_mcp_servers', connect)
    row = next(row for row in mcp_presets_payload(config_path=config_path)['presets'] if row['name'] == 'fixture')
    assert row['available'] is True and row['status'] == 'configured'
    result = await mcp_presets_test_action({'name': ['fixture']}, config_path=config_path)
    assert result['last_action']['ok'] is True
    assert len(calls) == 1
    assert calls[0].cwd == cfg.cwd
    closed.assert_awaited_once()
