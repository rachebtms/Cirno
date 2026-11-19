"""Settings dependency checks must follow the runtime's selected transport."""

from types import SimpleNamespace

import pytest
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.inspection import mcp_presets_test_action


@pytest.mark.parametrize("values,transport", [
    ({}, None), ({"command": "fixture"}, "stdio"),
    ({"command": "fixture", "url": "https://fixture.test/sse"}, "stdio"),
    ({"url": "https://fixture.test/sse/"}, "sse"),
    ({"url": "https://fixture.test/mcp"}, "streamableHttp"),
    ({"type": "stdio", "url": "https://fixture.test/mcp"}, "stdio"),
    ({"type": "sse", "command": "ignored"}, "sse"),
    ({"type": "streamableHttp", "command": "ignored"}, "streamableHttp"),
])
def test_transport_selection_preserves_runtime_precedence_and_is_not_persisted(values, transport):
    cfg = MCPServerConfig(**values)
    assert cfg.transport_type == transport
    assert "transport_type" not in cfg.model_dump()


@pytest.mark.parametrize("name,transport,remote", [
    ("fixture", "streamableHttp", True), ("fixture", "sse", True),
    ("context7", "streamableHttp", True),
    ("context7", "sse", True), ("context7", "stdio", False),
    ("fixture", "stdio", False), ("fixture", None, False),
])
async def test_ignored_stdio_command_cannot_block_remote_inspection(
    tmp_path, monkeypatch, name, transport, remote
):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers[name] = MCPServerConfig(
        type=transport, command="obsolete-uninstalled-command", url="https://fixture.test/mcp"
    )
    save_config(config, path)
    monkeypatch.setattr("cirno_server.webui.mcp.fields.command_available", lambda _, **_context: False)
    monkeypatch.setattr("cirno_server.webui.mcp.catalog.command_available", lambda _, **_context: False)
    monkeypatch.setattr("cirno_server.webui.mcp.inspection.command_available", lambda _, **_context: False)
    connected = []

    async def close():
        pass

    async def connect(servers, registry, **kwargs):
        connected.append(True)
        return {name: SimpleNamespace(aclose=close)}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    payload = mcp_presets_payload(config_path=path)
    row = next(row for row in payload["presets"] if row["name"] == name)
    assert row["available"] is remote
    assert row["status"] == ("configured" if remote else "missing_dependency")
    assert row["transport"] == (transport or "stdio")
    assert row["connection_summary"] == (
        "https://fixture.test/mcp" if remote else "obsolete-uninstalled-command"
    )
    result = await mcp_presets_test_action({"name": [name]}, config_path=path)
    assert result["last_action"]["ok"] is remote
    assert bool(connected) is remote
