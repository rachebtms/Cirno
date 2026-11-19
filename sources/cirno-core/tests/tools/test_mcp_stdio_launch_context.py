"""Connection launch parameters are verified with fake SDK contexts only."""

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.mcp import connector
from cirno_core.agent.tools.mcp.connections import close_mcp_connections
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.tools import MCPServerConfig


@pytest.mark.parametrize('kind', ['relative-command', 'custom-path', 'relative-path', 'missing-path'])
async def test_connector_passes_the_executable_owned_by_its_launch_context(tmp_path, monkeypatch, kind):
    directory = tmp_path / 'owned'
    directory.mkdir()
    executable = directory / ('fixture-mcp.exe' if os.name == 'nt' else 'fixture-mcp')
    executable.write_text('fixture, never executed')
    executable.chmod(0o700)
    other = tmp_path / 'other'
    other.mkdir()
    (other / executable.name).write_text('wrong executable, never executed')
    (other / executable.name).chmod(0o700)
    monkeypatch.setenv('PATH', str(other))
    if kind == 'relative-command':
        cfg = MCPServerConfig(command=f'./{executable.name}', cwd=str(directory), args=['literal arg'])
    elif kind == 'custom-path':
        cfg = MCPServerConfig(command=executable.name, env={'PATH': str(directory)}, args=['literal arg'])
    elif kind == 'relative-path':
        cfg = MCPServerConfig(command=executable.name, cwd=str(tmp_path), env={'PATH': 'owned'}, args=['literal arg'])
    else:
        cfg = MCPServerConfig(command=executable.name, env={'PATH': str(tmp_path / 'no-executable')})
    observed = []
    owner_thread = threading.get_ident()
    locate = connector.locate_stdio_command
    def locate_in_worker(*args, **kwargs):
        assert threading.get_ident() != owner_thread, 'Command discovery blocked the event loop'
        return locate(*args, **kwargs)
    monkeypatch.setattr(connector, 'locate_stdio_command', locate_in_worker)

    @asynccontextmanager
    async def stdio(params):
        observed.append(params)
        yield object(), object()

    @asynccontextmanager
    async def session(read, write):
        yield SimpleNamespace(initialize=AsyncMock(return_value=SimpleNamespace(capabilities=object())))

    def forbidden(*args, **kwargs):
        raise AssertionError('must not create a real SDK transport/client')

    modules = {
        'mcp': {'ClientSession': session, 'StdioServerParameters': lambda **kwargs: SimpleNamespace(**kwargs)},
        'mcp.client': {}, 'mcp.client.stdio': {'stdio_client': stdio},
        'mcp.client.sse': {'sse_client': forbidden},
        'mcp.client.streamable_http': {'streamable_http_client': forbidden},
    }
    for name, fields in modules.items():
        module = ModuleType(name)
        module.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(connector, 'register_capabilities', AsyncMock(return_value=0))
    monkeypatch.setattr(connector, '_filter_malformed_mcp_progress_notifications', lambda stream, name: stream)
    connections = await connector.connect_mcp_servers({'fixture': cfg}, ToolRegistry())
    try:
        if kind == 'missing-path':
            assert connections == {}
            assert observed == []
            return
        assert set(connections) == {'fixture'}
        assert len(observed) == 1
        assert Path(observed[0].command) == executable
        assert observed[0].args == cfg.args
        assert observed[0].cwd == (cfg.cwd or None)
        assert observed[0].env == (cfg.env or None)
    finally:
        assert await close_mcp_connections(connections) == {}
