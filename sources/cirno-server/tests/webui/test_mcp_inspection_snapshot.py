"""An inspection inventory belongs to the connection that was actually tested."""

from types import SimpleNamespace

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.inspection import mcp_presets_test_action


@pytest.mark.parametrize("change,stale", [
    ("url", True), ("headers", True), ("remove", True), ("proxy", True),
    ("scope", False), ("unrelated", False), ("unused_proxy", False),
])
async def test_inflight_inspection_does_not_project_old_inventory_on_new_config(
    tmp_path, monkeypatch, change, stale
):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["fixture"] = MCPServerConfig(
        type="streamableHttp", url="https://old.test/mcp", use_proxy=change == "proxy"
    )
    config.network.proxy = "http://old-proxy.test:8080"
    save_config(config, path)
    closed = []

    async def close():
        closed.append(True)

    async def connect(servers, registry, **kwargs):
        assert servers["fixture"].url == "https://old.test/mcp"
        current = load_config(path)
        cfg = current.tools.mcp_servers["fixture"]
        if change == "url":
            cfg.url = "https://new.test/mcp"
        elif change == "headers":
            cfg.headers = {"Authorization": "Bearer new-secret"}
        elif change == "remove":
            current.tools.mcp_servers.pop("fixture")
        elif change in {"proxy", "unused_proxy"}:
            current.network.proxy = "http://new-proxy.test:8080"
        elif change == "scope":
            cfg.enabled_tools = []
        else:
            current.tools.mcp_servers["other"] = MCPServerConfig(url="https://other.test/mcp")
        save_config(current, path)
        registry.register(SimpleNamespace(
            name="mcp_fixture_old_tool",
            to_schema=lambda: {"name": "mcp_fixture_old_tool", "description": "", "parameters": {}},
        ))
        return {"fixture": SimpleNamespace(aclose=close)}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    result = await mcp_presets_test_action({"name": ["fixture"]}, config_path=path)
    assert closed == [True]
    assert result["last_action"]["ok"] is not stale
    assert bool(result["last_action"].get("inventory_stale")) is stale
    if stale:
        assert "mcp_fixture_old_tool" not in str(result)
        assert "new-secret" not in str(result)
    if change != "remove":
        row = next(row for row in result["presets"] if row["name"] == "fixture")
        assert bool(row.get("inventory_stale")) is stale
        if not stale:
            assert row["tool_names"] == ["mcp_fixture_old_tool"]
