"""An empty inspection is an observed inventory, distinct from a catalog read."""

import pytest
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.inspection import mcp_presets_test_action


@pytest.mark.parametrize("name", ["fixture-docs", "context7"])
async def test_empty_successful_inspection_projects_timestamp_and_inventory_to_its_row(tmp_path, monkeypatch, name):
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers[name] = MCPServerConfig(type="streamableHttp", url="https://fixture.test/mcp")
    path = tmp_path / "config.json"
    save_config(config, path)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", path)

    class Connection:
        closed = False

        async def aclose(self):
            self.closed = True

    connection = Connection()

    async def connect(_servers, _registry, **kwargs):
        return {name: connection}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    payload = await mcp_presets_test_action({"name": [name]}, config_path=path)
    assert payload["last_action"]["ok"] is True
    row = next(item for item in payload["presets"] if item["name"] == name)
    assert row["tool_names"] == []
    assert row["tool_count"] == 0
    assert row["checked_at"] == payload["last_action"]["checked_at"]
    assert connection.closed
    for other in payload["presets"]:
        if other["name"] != name:
            assert "checked_at" not in other
